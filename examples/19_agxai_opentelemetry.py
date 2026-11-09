"""Export an agxai-instrumented, BehaviorWeave-guarded workflow as OpenTelemetry traces.

The guarded agent runs inside an agxai-instrumented workflow. ``BehaviorWeaveObservability``
sits in front of agxai's ``OpenTelemetryObservability``: it runs every captured event through
an audit engine and forwards the full stream to OpenTelemetry, which exports one span per
node execution, tool execution, and state transition.

With ``OTEL_EXPORTER_OTLP_ENDPOINT`` set, spans are exported over OTLP/HTTP, for example to an
OpenTelemetry Collector or straight to Jaeger; otherwise each span name is printed.

Run:
    podman run -d --name behaviorweave-jaeger -p 16686:16686 -p 4318:4318 \
        docker.io/jaegertracing/jaeger:2.17.0
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
    uv sync --group examples
    uv run python examples/19_agxai_opentelemetry.py

Then open http://localhost:16686 and search the ``behaviorweave-example`` service.
"""

import asyncio
import os
from typing import TypedDict

from agxai import CanonicalEvent, OpenTelemetryObservability
from langgraph.graph import END, START, StateGraph
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanProcessor,
)

from behaviorweave import BehaviorEngine, InterventionDecision, InterventionType, PolicyRule
from behaviorweave.integrations.agxai import (
    BehaviorWeaveObservability,
    create_agxai_runtime,
    instrument_graph,
)
from common import ask, guarded_agent, repeat_guard_policies

SERVICE = "behaviorweave-example"


class IncidentState(TypedDict):
    """Workflow state: the incident request and the agent's answer."""

    request: str
    answer: str


def span_processor() -> SpanProcessor:
    """Export over OTLP/HTTP when an endpoint is configured, else print each span name."""
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return BatchSpanProcessor(OTLPSpanExporter())
    return SimpleSpanProcessor(ConsoleSpanExporter(formatter=lambda span: f"span: {span.name}\n"))


def print_audit(event: CanonicalEvent, decision: InterventionDecision) -> None:
    if decision.actionable:
        print(f"audit: {decision.intervention.reason} ({event.event_type})")


async def main() -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE}))
    provider.add_span_processor(span_processor())
    auditor = BehaviorEngine(
        policies=[
            PolicyRule("duplicate-tool-call", "repeated_tool_call", 2, InterventionType.WARNING)
        ]
    )
    runtime = create_agxai_runtime(
        application_id=SERVICE,
        graph_id="incident",
        observability=BehaviorWeaveObservability(
            auditor,
            delegate=OpenTelemetryObservability(tracer_provider=provider, owns_provider=True),
            on_decision=print_audit,
        ),
    )
    agent = guarded_agent(BehaviorEngine(policies=repeat_guard_policies()))

    async def investigate(state: IncidentState) -> dict[str, str]:
        result = await ask(
            agent,
            f"{state['request']} Check get_alarm three times, one call at a time, then summarize.",
            thread_id="example-19",
        )
        return {"answer": result["messages"][-1].text}

    builder = StateGraph(IncidentState)
    builder.add_node("investigate", investigate)
    builder.add_edge(START, "investigate")
    builder.add_edge("investigate", END)
    graph = instrument_graph(builder.compile(), runtime=runtime)
    try:
        with provider.get_tracer(SERVICE).start_as_current_span("incident"):
            result = await graph.ainvoke(
                {"request": "Assess the ETCH-3 pressure alarm.", "answer": ""}
            )
        print(f"Answer:\n{result['answer']}")
    finally:
        await runtime.close()
    if endpoint := os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        print(f"Spans exported to {endpoint} as service {SERVICE}.")


if __name__ == "__main__":
    asyncio.run(main())
