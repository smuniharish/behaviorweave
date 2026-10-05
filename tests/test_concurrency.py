import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from behaviorweave import BehaviorEngine, BehaviorEvent, EventType, InterventionType, PolicyRule
from support import RecordingStore

WORKERS = 32


def _run_concurrently(engine: BehaviorEngine, events: list[BehaviorEvent]) -> list[str]:
    barrier = threading.Barrier(WORKERS)

    def worker(index: int) -> list[str]:
        barrier.wait()
        return [engine.process(event).intervention.kind.value for event in events[index::WORKERS]]

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return [kind for kinds in pool.map(worker, range(WORKERS)) for kind in kinds]


def test_no_updates_are_lost_while_cooldowns_are_written() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "nudge",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                cooldown=timedelta(milliseconds=1),
            )
        ],
        state_store=store,
    )
    events = [BehaviorEvent.tool_call("t", scope="s", event_id=str(i)) for i in range(640)]
    _run_concurrently(engine, events)
    assert store.count("s", "repeated_tool_call") == 640


def test_once_only_policy_fires_exactly_once_under_contention() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True)
        ]
    )
    events = [BehaviorEvent.tool_call("t", scope="s", event_id=str(i)) for i in range(WORKERS * 8)]
    kinds = _run_concurrently(engine, events)
    assert kinds.count("nudge") == 1
    assert kinds.count("noop") == len(events) - 1


def test_concurrent_duplicates_are_counted_once() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_node_execution", 99, InterventionType.NUDGE)],
        state_store=store,
    )
    events = [
        BehaviorEvent(EventType.NODE_EXECUTION, scope="s", node_name="worker", event_id=str(i % 50))
        for i in range(WORKERS * 10)
    ]
    _run_concurrently(engine, events)
    assert store.count("s", "repeated_node_execution") == 50


async def test_async_fan_out_shares_one_engine() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1000, InterventionType.NUDGE)],
        state_store=store,
    )
    events = [BehaviorEvent.tool_call("t", scope=f"conv-{i % 4}") for i in range(200)]
    await asyncio.gather(*(asyncio.to_thread(engine.process, event) for event in events))
    assert [store.count(f"conv-{i}", "repeated_tool_call") for i in range(4)] == [50] * 4
