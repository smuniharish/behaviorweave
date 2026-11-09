"""Keep behavioral history isolated per conversation, and release it when one ends.

One agent and one engine serve two conversations. The middleware scopes history by the
LangGraph ``thread_id``, so repeated calls in conversation A never affect conversation B. When
conversation A ends, ``expire_scope`` releases its behavioral history.

Run:
    uv sync --group examples
    uv run python examples/13_multi_scope.py
"""

import asyncio

from behaviorweave import BehaviorEngine
from common import ask, guarded_agent, print_run, repeat_guard_policies


async def main() -> None:
    engine = BehaviorEngine(policies=repeat_guard_policies())
    agent = guarded_agent(engine)
    print("Conversation A")
    print_run(
        await ask(
            agent,
            "Call get_alarm for ETCH-3 twice, one call at a time, then summarize.",
            thread_id="user-a",
        )
    )
    released = await engine.expire_scope("user-a")
    print(f"\nConversation A ended; released {released} behavior state(s).")
    print("\nConversation B")
    print_run(await ask(agent, "Call get_alarm for ETCH-3 once and summarize.", thread_id="user-b"))
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
