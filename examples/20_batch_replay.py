"""Re-evaluate recorded agent activity in a batch, then release the finished conversations.

A nightly job replays yesterday's recorded tool calls from three conversations through the
current policies. ``process_many`` processes each conversation's events in their recorded
order while different conversations run concurrently, and returns the decisions in input
order. A ``CompositeAuditSink`` delivers every audit record both to a review queue and to an
intervention tally. Replaying the batch again changes nothing, because delivery is
idempotent; afterwards ``expire_scope`` releases each finished conversation's history.

The job needs no model or service.

Run:
    uv sync --group examples
    uv run python examples/20_batch_replay.py
"""

import asyncio
from collections import Counter

from behaviorweave import (
    AuditRecord,
    AuditSink,
    BehaviorEngine,
    BehaviorEvent,
    CompositeAuditSink,
    InMemoryAuditSink,
)
from common import repeat_guard_policies

RECORDED = [
    ("conversation-1", "get_alarm", "ETCH-3"),
    ("conversation-2", "get_alarm", "ETCH-1"),
    ("conversation-1", "get_alarm", "ETCH-3"),
    ("conversation-3", "search_incident_history", "ETCH-2"),
    ("conversation-1", "get_alarm", "ETCH-3"),
    ("conversation-2", "search_incident_history", "ETCH-1"),
]


class InterventionTally(AuditSink):
    """Counts first-time actionable decisions by intervention kind."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    async def write(self, record: AuditRecord) -> None:
        """Count ``record`` when its decision is actionable and not a redelivery."""
        decision = record.decision
        if decision.actionable and not decision.duplicate:
            self.counts[decision.intervention.kind.value] += 1


async def main() -> None:
    events = [
        BehaviorEvent.tool_call(
            tool, {"machine": machine}, scope=scope, event_id=f"{scope}:{index}"
        )
        for index, (scope, tool, machine) in enumerate(RECORDED)
    ]
    review, tally = InMemoryAuditSink(), InterventionTally()
    engine = BehaviorEngine(
        policies=repeat_guard_policies(), audit_sink=CompositeAuditSink(review, tally)
    )
    async with engine:
        decisions = await engine.process_many(events, concurrency=8)
        for event, decision in zip(events, decisions, strict=True):
            print(f"{event.scope} {event.tool_name}: {decision.intervention.kind}")

        replay = await engine.process_many(events)
        duplicates = sum(decision.duplicate for decision in replay)
        print(f"\nReplay: {duplicates} of {len(replay)} decisions marked duplicate.")
        print(f"Review queue: {len(review.records)} audit records.")
        print(f"Interventions: {dict(sorted(tally.counts.items()))}")

        for scope in sorted({event.scope for event in events}):
            released = await engine.expire_scope(scope)
            print(f"Released {scope}: {released} behavior state(s).")


if __name__ == "__main__":
    asyncio.run(main())
