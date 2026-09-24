"""Live Deep Agents subagent delegation example.

Run:
    uv sync --extra examples --extra real-model
    $env:EXPLABS_API_KEY = "<credential>"
    uv run python examples/07_deepagents_subagents.py
"""

from common import alarm_tools, create_explabs_model, default_guard
from deepagents import SubAgent, create_deep_agent


def main() -> None:
    guard = default_guard(scope="live-deep-agent-subagents")
    model = create_explabs_model()
    agent = create_deep_agent(
        model=model,
        tools=alarm_tools(guard),
        subagents=[
            SubAgent(
                name="incident_researcher",
                description="Collect alarm and incident-history evidence for one machine.",
                model=model,
                tools=alarm_tools(guard),
            ),
            SubAgent(
                name="incident_analyst",
                description="Assess supplied operational evidence and recommend next action.",
                model=model,
            ),
        ],
        system_prompt=(
            "Delegate evidence collection once to incident_researcher and analysis once to "
            "incident_analyst, then synthesize their findings. Respect BehaviorWeave guidance."
        ),
    )
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Delegate an ETCH-3 pressure investigation and summarize the result.",
                }
            ]
        }
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
