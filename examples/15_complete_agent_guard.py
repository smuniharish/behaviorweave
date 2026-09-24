"""Flagship live graph: LangGraph + langgraph-xai + guarded real LangChain agent."""

from typing import TypedDict

from common import invoke_live_agent
from langgraph.graph import END, START, StateGraph

from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter


class GuardedRunState(TypedDict):
    request: str
    answer: str


def guarded_agent_node(state: GuardedRunState) -> dict[str, str]:
    result = invoke_live_agent(
        (
            f"{state['request']} Investigate with get_alarm and search_incident_history. "
            "If you receive a BehaviorWeave nudge, warning, or force-synthesis guidance, "
            "obey it and produce a concise final answer from collected evidence."
        ),
        scope="flagship-live-guard",
    )
    return {"answer": str(result["messages"][-1].content)}


def main() -> None:
    builder = StateGraph(GuardedRunState)
    builder.add_node("guarded_agent", guarded_agent_node)
    builder.add_edge(START, "guarded_agent")
    builder.add_edge("guarded_agent", END)
    graph = builder.compile()
    observable_graph = LangGraphXAIEventAdapter.instrument_graph(
        graph,
        application_id="behaviorweave-example",
        tenant_id="local-demo",
        graph_id="complete-agent-guard",
    )
    result = observable_graph.invoke({"request": "Assess the ETCH-3 pressure alarm."})
    print(result["answer"])


if __name__ == "__main__":
    main()
