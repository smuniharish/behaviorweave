"""Flagship: a guarded agent inside an explainable LangGraph workflow.

1. A LangGraph workflow runs a LangChain agent whose tool calls are guarded by
   BehaviorWeaveMiddleware.
2. The workflow is instrumented with langgraph-xai, which records provenance for every node
   and tool execution.
3. After the run, its recorded tool executions are mapped back into BehaviorWeave with
   ``LangGraphXAIEventAdapter``, producing an audit whose decisions link to their provenance.

Run:
    uv sync --group examples
    uv run python examples/15_complete_agent_guard.py
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph_xai import ProvenanceStore, Run, StoreFilter, XAIRuntime
from langgraph_xai.core import ToolExecutionEvent

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter
from common import ask, guarded_agent, repeat_guard_policies

APPLICATION, TENANT = "behaviorweave-example", "local-demo"


class IncidentState(TypedDict):
    """Workflow state: the incident request and the agent's answer."""

    request: str
    answer: str


agent = guarded_agent(BehaviorEngine(policies=repeat_guard_policies()))


def investigate(state: IncidentState) -> dict[str, str]:
    result = ask(
        agent,
        f"{state['request']} Check get_alarm twice to confirm, review the incident history, "
        "and give a concise recommendation.",
        thread_id="example-15",
    )
    return {"answer": result["messages"][-1].text}


async def provenance_audit(runtime: XAIRuntime, run: Run) -> None:
    """Replay the run's recorded tool executions through an audit engine."""
    store = runtime.registry.get(ProvenanceStore)
    assert store is not None
    auditor = BehaviorEngine(
        policies=[PolicyRule("tool-usage", "event_frequency", 2, InterventionType.WARNING)]
    )
    adapter = LangGraphXAIEventAdapter()
    query = StoreFilter(
        application_id=APPLICATION,
        tenant_id=TENANT,
        run_id=run.run_id,
        item_type=ToolExecutionEvent,
    )
    async for record in store.query(query):
        decision = auditor.process(adapter.event(record, scope="audit"))
        if decision.actionable and decision.explanation is not None:
            print(
                f"audit: {decision.intervention.reason} "
                f"(provenance {decision.explanation.provenance_ref})"
            )


def main() -> None:
    builder = StateGraph(IncidentState)
    builder.add_node("investigate", investigate)
    builder.add_edge(START, "investigate")
    builder.add_edge("investigate", END)
    runtime = XAIRuntime(application_id=APPLICATION, tenant_id=TENANT, graph_id="incident")
    graph = LangGraphXAIEventAdapter.instrument_graph(builder.compile(), runtime=runtime)
    try:
        with runtime.collect_runs() as runs:
            result = graph.invoke({"request": "Assess the ETCH-3 pressure alarm.", "answer": ""})
        print(f"Answer:\n{result['answer']}\n")
        (run,) = runs
        runtime.run_sync(provenance_audit(runtime, run))
    finally:
        runtime.run_sync(runtime.close())


if __name__ == "__main__":
    main()
