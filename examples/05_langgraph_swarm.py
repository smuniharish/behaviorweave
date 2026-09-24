"""Live langgraph-swarm example with real agents and handoff tools.

Run:
    uv sync --extra examples --extra real-model
    $env:EXPLABS_API_KEY = "<credential>"
    uv run python examples/05_langgraph_swarm.py
"""

from common import create_explabs_model, create_langchain_agent
from langgraph_swarm import create_handoff_tool, create_swarm


def main() -> None:
    model = create_explabs_model()
    alarm_agent = create_langchain_agent(
        model,
        [create_handoff_tool(agent_name="history_agent")],
        name="alarm_agent",
    )
    history_agent = create_langchain_agent(
        model,
        [create_handoff_tool(agent_name="alarm_agent")],
        name="history_agent",
    )
    swarm = create_swarm(
        [alarm_agent, history_agent],
        default_active_agent="alarm_agent",
    ).compile()
    result = swarm.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Start with the alarm agent, hand off once to the history agent for "
                        "context, then return a concise ETCH-3 recommendation."
                    ),
                }
            ]
        }
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
