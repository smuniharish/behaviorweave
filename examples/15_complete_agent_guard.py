"""Flagship: a guarded agent inside an explainable, agxai-instrumented LangGraph workflow.

1. A LangGraph workflow runs a LangChain agent whose tool calls are guarded by
   BehaviorWeaveMiddleware.
2. The workflow is instrumented with agxai, which records provenance for every node and tool
   execution.
3. The guard engine writes its audit trail to ``AgxaiAuditSink``, so every intervention is
   recorded in the agxai run as evidence and a decision that its explanations cover.
4. ``BehaviorWeaveObservability`` feeds every event agxai captures to a second, audit-only
   engine, whose decisions link back to the provenance of the events that triggered them.

Run:
    uv sync --group examples
    uv run python examples/15_complete_agent_guard.py
"""

import asyncio
from typing import TypedDict

from agxai import CanonicalEvent
from langgraph.graph import END, START, StateGraph

from behaviorweave import BehaviorEngine, InterventionDecision, InterventionType, PolicyRule
from behaviorweave.integrations.agxai import (
    AgxaiAuditSink,
    BehaviorWeaveObservability,
    create_agxai_runtime,
    instrument_graph,
)
from common import ask, guarded_agent, repeat_guard_policies


class IncidentState(TypedDict):
    """Workflow state: the incident request and the agent's answer."""

    request: str
    answer: str


def print_audit(event: CanonicalEvent, decision: InterventionDecision) -> None:
    if decision.actionable and decision.explanation is not None:
        print(
            f"audit: {decision.intervention.reason} "
            f"({event.event_type}, provenance {decision.explanation.provenance_ref})"
        )


async def main() -> None:
    auditor = BehaviorEngine(
        policies=[
            PolicyRule("duplicate-tool-call", "repeated_tool_call", 2, InterventionType.WARNING)
        ]
    )
    runtime = create_agxai_runtime(
        application_id="behaviorweave-example",
        tenant_id="local-demo",
        graph_id="incident",
        observability=BehaviorWeaveObservability(auditor, on_decision=print_audit),
    )
    guard = BehaviorEngine(policies=repeat_guard_policies(), audit_sink=AgxaiAuditSink(runtime))
    agent = guarded_agent(guard)

    async def investigate(state: IncidentState) -> dict[str, str]:
        result = await ask(
            agent,
            f"{state['request']} Check get_alarm twice to confirm, review the incident "
            "history, and give a concise recommendation.",
            thread_id="example-15",
        )
        return {"answer": result["messages"][-1].text}

    builder = StateGraph(IncidentState)
    builder.add_node("investigate", investigate)
    builder.add_edge(START, "investigate")
    builder.add_edge("investigate", END)
    graph = instrument_graph(builder.compile(), runtime=runtime)
    try:
        with runtime.collect_runs() as runs:
            result = await graph.ainvoke(
                {"request": "Assess the ETCH-3 pressure alarm.", "answer": ""}
            )
        print(f"Answer:\n{result['answer']}\n")
        (run,) = runs
        for decision in run.decisions:
            if decision.decision_type == "behavior_intervention":
                print(
                    f"recorded in run {run.run_id}: {decision.selected_action} "
                    f"by policy {', '.join(decision.policy_references)}"
                )
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
