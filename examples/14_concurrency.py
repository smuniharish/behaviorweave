"""Share one BehaviorWeave engine across concurrent live agent runs.

Each worker runs its own provider-backed agent, but all of them report to one engine and one
shared scope. An audit sink counts every observed tool call; because state updates are
atomic, the count equals the number of tool calls the workers made. This example incurs one
agent run per worker; set ``BEHAVIORWEAVE_CONCURRENCY_CALLS`` to change the load (default 10).

Run:
    uv sync --group examples
    uv run python examples/14_concurrency.py
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from behaviorweave import AuditRecord, BehaviorEngine, EventType, InterventionType, PolicyRule
from common import ask, create_model, guarded_agent


class ToolCallCounter:
    """Thread-safe audit sink counting observed tool calls."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = Lock()

    def __call__(self, record: AuditRecord) -> None:
        """Count ``record`` if it observed a tool call."""
        if record.event.event_type is EventType.TOOL_CALL:
            with self._lock:
                self.count += 1


def main() -> None:
    workers = int(os.environ.get("BEHAVIORWEAVE_CONCURRENCY_CALLS", "10"))
    counter = ToolCallCounter()
    engine = BehaviorEngine(
        policies=[PolicyRule("fleet-watch", "event_frequency", 10_000, InterventionType.WARNING)],
        audit_sink=counter,
    )
    agent = guarded_agent(engine, model=create_model(), scope="shared-fleet")

    def work(index: int) -> int:
        result = ask(
            agent,
            f"Call get_alarm exactly once for machine ETCH-{index}, then summarize it.",
            thread_id=f"worker-{index}",
        )
        return sum(1 for message in result["messages"] if message.type == "tool")

    with ThreadPoolExecutor(max_workers=min(workers, 16)) as pool:
        tool_results = sum(pool.map(work, range(workers)))

    print(f"{workers} concurrent agent runs returned {tool_results} tool results.")
    print(f"BehaviorWeave observed {counter.count} tool calls in the shared scope.")


if __name__ == "__main__":
    main()
