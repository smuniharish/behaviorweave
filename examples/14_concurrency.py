"""Share one BehaviorWeave engine across concurrent live agent runs.

Each task runs its own provider-backed agent, but all of them report to one engine and one
shared scope. An audit sink counts every observed tool call; because state updates are
atomic, the count equals the number of tool calls the agents made. This example incurs one
agent run per task; set ``BEHAVIORWEAVE_CONCURRENCY_CALLS`` to change the load (default 10).

Run:
    uv sync --group examples
    uv run python examples/14_concurrency.py
"""

import asyncio
import os

from behaviorweave import (
    AuditRecord,
    AuditSink,
    BehaviorEngine,
    EventType,
    InterventionType,
    PolicyRule,
)
from common import ask, create_model, guarded_agent


class ToolCallCounter(AuditSink):
    """Audit sink counting observed tool calls."""

    def __init__(self) -> None:
        self.count = 0

    async def write(self, record: AuditRecord) -> None:
        """Count ``record`` if it observed a tool call."""
        if record.event.event_type is EventType.TOOL_CALL:
            self.count += 1


async def main() -> None:
    runs = int(os.environ.get("BEHAVIORWEAVE_CONCURRENCY_CALLS", "10"))
    counter = ToolCallCounter()
    engine = BehaviorEngine(
        policies=[PolicyRule("fleet-watch", "event_frequency", 10_000, InterventionType.WARNING)],
        audit_sink=counter,
    )
    agent = guarded_agent(engine, model=create_model(), scope="shared-fleet")
    limit = asyncio.Semaphore(16)

    async def work(index: int) -> int:
        async with limit:
            result = await ask(
                agent,
                f"Call get_alarm exactly once for machine ETCH-{index}, then summarize it.",
                thread_id=f"worker-{index}",
            )
        return sum(1 for message in result["messages"] if message.type == "tool")

    tool_results = sum(await asyncio.gather(*(work(index) for index in range(runs))))
    print(f"{runs} concurrent agent runs returned {tool_results} tool results.")
    print(f"BehaviorWeave observed {counter.count} tool calls in the shared scope.")


if __name__ == "__main__":
    asyncio.run(main())
