"""Export an agxai-instrumented, BehaviorWeave-guarded workflow as OpenTelemetry signals.

The guarded agent runs inside an agxai-instrumented workflow. ``BehaviorWeaveObservability``
sits in front of agxai's ``OpenTelemetryObservability``: it runs every captured event through
an audit engine and forwards the full stream to OpenTelemetry, which exports one span per
node execution, tool execution, and state transition. The audit engine's
``OpenTelemetryMetricsSink`` counts its decisions in the ``behaviorweave.decisions`` metric.

With ``OTEL_EXPORTER_OTLP_ENDPOINT`` set, spans and metrics are exported over OTLP/HTTP to an
OpenTelemetry Collector; otherwise each span name and decision count is printed.

Run (``examples/otel-collector.yaml`` sends traces to Jaeger and prints metrics):
    podman network create bw-net
    podman run -d --name bw-jaeger --network bw-net -p 16686:16686 \
        docker.io/jaegertracing/jaeger:2.17.0
    podman run -d --name bw-otel --network bw-net -p 4318:4318 \
        -v ./examples/otel-collector.yaml:/etc/otelcol/config.yaml:ro \
        docker.io/otel/opentelemetry-collector:latest
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
    uv sync --group examples
    uv run python examples/19_agxai_opentelemetry.py

Then open http://localhost:16686 and search the ``behaviorweave-example`` service, and see
the decision counts with ``podman logs bw-otel``.
"""

import asyncio
import os
from typing import TypedDict

from agxai import CanonicalEvent, OpenTelemetryObservability
from langgraph.graph import END, START, StateGraph
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    MetricReader,
    NumberDataPoint,
    PeriodicExportingMetricReader,
)
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
from behaviorweave.integrations.opentelemetry import OpenTelemetryMetricsSink
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


def metric_reader() -> MetricReader:
    """Export over OTLP/HTTP when an endpoint is configured, else keep metrics in memory."""
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return PeriodicExportingMetricReader(OTLPMetricExporter())
    return InMemoryMetricReader()


def print_decision_counts(reader: InMemoryMetricReader) -> None:
    data = reader.get_metrics_data()
    for resource in data.resource_metrics if data is not None else ():
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                for point in metric.data.data_points:
                    if not isinstance(point, NumberDataPoint):
                        continue
                    attributes = point.attributes or {}
                    event = attributes.get("behaviorweave.event.type")
                    kind = attributes.get("behaviorweave.intervention")
                    print(f"metric: {metric.name} {event} -> {kind}: {point.value}")


def print_audit(event: CanonicalEvent, decision: InterventionDecision) -> None:
    if decision.actionable:
        print(f"audit: {decision.intervention.reason} ({event.event_type})")


async def main() -> None:
    resource = Resource.create({"service.name": SERVICE})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(span_processor())
    reader = metric_reader()
    meter_provider = MeterProvider(metric_readers=[reader], resource=resource)
    auditor = BehaviorEngine(
        policies=[
            PolicyRule("duplicate-tool-call", "repeated_tool_call", 2, InterventionType.WARNING)
        ],
        audit_sink=OpenTelemetryMetricsSink(meter_provider=meter_provider),
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
        await auditor.close()
        if isinstance(reader, InMemoryMetricReader):
            print_decision_counts(reader)
        meter_provider.shutdown()
    if endpoint := os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        print(f"Spans and metrics exported to {endpoint} as service {SERVICE}.")


if __name__ == "__main__":
    asyncio.run(main())
