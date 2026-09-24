"""Live explicit LangGraph workflow whose agent node is BehaviorWeave-guarded."""

from typing import TypedDict

from common import invoke_live_agent
from langgraph.graph import END, START, StateGraph


class IncidentState(TypedDict):
    request: str
    report: str


def investigate(state: IncidentState) -> dict[str, str]:
    result = invoke_live_agent(
        (
            f"{state['request']} Use get_alarm exactly once and use incident history once. "
            "If a BehaviorWeave intervention appears, follow it."
        ),
        scope="langgraph-custom-graph",
    )
    return {"report": str(result["messages"][-1].content)}


def main() -> None:
    builder = StateGraph(IncidentState)
    builder.add_node("investigate", investigate)
    builder.add_edge(START, "investigate")
    builder.add_edge("investigate", END)
    graph = builder.compile()
    result = graph.invoke({"request": "Produce an ETCH-3 operational incident report."})
    print(result["report"])


if __name__ == "__main__":
    main()
