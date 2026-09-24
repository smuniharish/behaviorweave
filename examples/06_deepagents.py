"""Live Deep Agents execution with real tools guarded by BehaviorWeave.

Run:
    uv sync --extra examples --extra real-model
    $env:EXPLABS_API_KEY = "<credential>"
    uv run python examples/06_deepagents.py
"""

from common import alarm_tools, create_explabs_model, default_guard
from deepagents import create_deep_agent


def main() -> None:
    guard = default_guard(scope="live-deep-agent")
    agent = create_deep_agent(
        model=create_explabs_model(),
        tools=alarm_tools(guard),
        system_prompt=(
            "Use the operational tools to investigate ETCH-3. Follow any BehaviorWeave "
            "intervention included in a tool response and synthesize the available evidence."
        ),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Investigate the ETCH-3 pressure alarm."}]}
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
