"""Keep behavioral history isolated per conversation.

One agent and one engine serve two conversations. The middleware scopes history by the
LangGraph ``thread_id``, so repeated calls in conversation A never affect conversation B.

Run:
    uv sync --group examples
    uv run python examples/13_multi_scope.py
"""

from behaviorweave import BehaviorEngine
from common import ask, guarded_agent, print_run, repeat_guard_policies


def main() -> None:
    agent = guarded_agent(BehaviorEngine(policies=repeat_guard_policies()))
    print("Conversation A")
    print_run(
        ask(
            agent,
            "Call get_alarm for ETCH-3 twice, one call at a time, then summarize.",
            thread_id="user-a",
        )
    )
    print("\nConversation B")
    print_run(ask(agent, "Call get_alarm for ETCH-3 once and summarize.", thread_id="user-b"))


if __name__ == "__main__":
    main()
