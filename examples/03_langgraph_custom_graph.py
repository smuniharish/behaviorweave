"""Bound a LangGraph revision loop with BehaviorWeave.

A writer node drafts an incident report and a reviewer node critiques it, looping until the
reviewer approves. BehaviorWeave observes each writer execution; once the writer has run
three times, the policy stops the loop and the graph routes to END with the latest draft.

Run:
    uv sync --group examples
    uv run python examples/03_langgraph_custom_graph.py
"""

from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph import LangGraphEventAdapter
from common import create_model


class ReportState(TypedDict):
    """Graph state: the request, the current draft, review feedback, and the stop reason."""

    request: str
    draft: str
    feedback: str
    stopped_by: str | None


engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "revision-budget",
            "event_frequency",
            4,
            InterventionType.STOP,
            message="Revision budget exhausted: publish the latest draft.",
        )
    ]
)
adapter = LangGraphEventAdapter()
model = create_model()


def _guard(node: str, config: RunnableConfig) -> str | None:
    scope = str(config.get("configurable", {}).get("thread_id", "report"))
    decision = engine.process(adapter.node(node, scope=scope))
    return decision.intervention.message if decision.intervention.kind.is_terminal else None


def write(state: ReportState, config: RunnableConfig) -> dict[str, object]:
    if stopped := _guard("write", config):
        return {"stopped_by": stopped}
    prompt = (
        f"Write a three-sentence incident report for: {state['request']}\n"
        f"Previous draft: {state['draft'] or 'none'}\n"
        f"Reviewer feedback: {state['feedback'] or 'none'}"
    )
    return {"draft": model.invoke(prompt).text}


def review(state: ReportState) -> dict[str, object]:
    prompt = (
        "You are an exacting reviewer. Reply with exactly one concrete improvement for this "
        f"incident report. Never reply APPROVED unless it is flawless.\n\n{state['draft']}"
    )
    return {"feedback": model.invoke(prompt).text}


def after_write(state: ReportState) -> str:
    return END if state["stopped_by"] else "review"


def after_review(state: ReportState) -> str:
    return END if "APPROVED" in state["feedback"].upper() else "write"


def main() -> None:
    builder = StateGraph(ReportState)
    builder.add_node("write", write)
    builder.add_node("review", review)
    builder.add_edge(START, "write")
    builder.add_conditional_edges("write", after_write)
    builder.add_conditional_edges("review", after_review)
    graph = builder.compile()
    result = graph.invoke(
        {
            "request": "ETCH-3 chamber-pressure alarm",
            "draft": "",
            "feedback": "",
            "stopped_by": None,
        },
        config={"configurable": {"thread_id": "example-03"}},
    )
    print(f"Stopped by: {result['stopped_by'] or 'reviewer approval'}\n")
    print(result["draft"])


if __name__ == "__main__":
    main()
