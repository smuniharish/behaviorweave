"""Guard a LangChain agent's tool calls with BehaviorWeaveMiddleware.

The agent is asked to call the same tool three times. BehaviorWeave appends a nudge to the
second identical result and blocks the third call before it reaches the tool.

Run:
    uv sync --group examples
    uv run python examples/01_langchain_agent.py
"""

from behaviorweave import BehaviorEngine
from common import ask, guarded_agent, print_run, repeat_guard_policies


def main() -> None:
    engine = BehaviorEngine(policies=repeat_guard_policies())
    agent = guarded_agent(engine)
    result = ask(
        agent,
        "Call get_alarm for ETCH-3 three times, one call at a time, then summarize the alarm.",
        thread_id="example-01",
    )
    print_run(result)


if __name__ == "__main__":
    main()
