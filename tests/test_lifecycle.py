"""Batch processing, scope expiry, and composite audit delivery."""

import asyncio

import pytest
from langgraph.store.memory import InMemoryStore

from behaviorweave import (
    AuditRecord,
    AuditSink,
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    CompositeAuditSink,
    EventValidationError,
    InMemoryAuditSink,
    InterventionType,
    PolicyConfigurationError,
    PolicyRule,
)
from behaviorweave.integrations.langgraph import LangGraphBehaviorStateStore
from behaviorweave.integrations.langgraph import store as store_module
from support import at

RULES = [
    PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
    PolicyRule("stop", "repeated_tool_call", 4, InterventionType.STOP),
]


def _tool(scope: str, index: int, name: str = "search") -> BehaviorEvent:
    return BehaviorEvent.tool_call(
        name, scope=scope, timestamp=at(index), event_id=f"{scope}:{index}"
    )


def _batch() -> list[BehaviorEvent]:
    # Interleaved scopes, each with a repeated call, a different call, and a redelivery.
    events = [_tool(scope, index) for index in range(4) for scope in ("a", "b", "c")]
    events.insert(5, _tool("b", 9, name="other"))
    events.append(_tool("a", 1))
    return events


def _engine(**options: object) -> BehaviorEngine:
    # pyrefly: ignore[bad-argument-type]
    return BehaviorEngine(policies=RULES, **options)


@pytest.mark.parametrize("concurrency", [1, 2, 16])
async def test_process_many_matches_sequential_processing(concurrency: int) -> None:
    events = _batch()
    sequential = _engine()
    expected = [await sequential.process(event) for event in events]
    decisions = await _engine().process_many(events, concurrency=concurrency)
    assert decisions == expected
    assert decisions[-1].duplicate, "a redelivered event in the batch is recognized"


async def test_process_many_bounds_scope_concurrency_and_serializes_each_scope() -> None:
    active: set[str] = set()
    peak = 0

    class SlowSink(AuditSink):
        async def write(self, record: AuditRecord) -> None:
            nonlocal peak
            scope = record.event.scope
            assert scope not in active, "events of one scope never overlap"
            active.add(scope)
            peak = max(peak, len(active))
            await asyncio.sleep(0.005)
            active.discard(scope)

    events = [_tool(f"s{scope}", index) for index in range(3) for scope in range(6)]
    decisions = await _engine(audit_sink=SlowSink()).process_many(events, concurrency=2)
    assert len(decisions) == len(events)
    assert peak == 2


async def test_process_many_handles_empty_and_generator_input() -> None:
    engine = _engine()
    assert await engine.process_many([]) == []
    decisions = await engine.process_many(_tool("g", index) for index in range(2))
    assert [d.intervention.kind for d in decisions] == [
        InterventionType.NOOP,
        InterventionType.NUDGE,
    ]


@pytest.mark.parametrize("concurrency", [0, -1, True, 1.5, "2"])
async def test_process_many_rejects_invalid_concurrency(concurrency: object) -> None:
    with pytest.raises(PolicyConfigurationError, match="concurrency must be a positive"):
        # pyrefly: ignore[bad-argument-type]
        await _engine().process_many([], concurrency=concurrency)


async def test_process_many_validates_every_event_before_processing() -> None:
    sink = InMemoryAuditSink()
    engine = _engine(audit_sink=sink)
    with pytest.raises(EventValidationError, match=r"events\[1\] must be a BehaviorEvent"):
        # pyrefly: ignore[bad-argument-type]
        await engine.process_many([_tool("a", 0), {"scope": "a"}])
    assert sink.records == (), "nothing is processed when validation fails"


async def test_process_many_raises_the_failure_and_a_retry_is_idempotent() -> None:
    attempts = 0

    class FlakySink(InMemoryAuditSink):
        async def write(self, record: AuditRecord) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 3:
                raise ConnectionError("audit backend unavailable")
            await super().write(record)

    events = [_tool("a", index) for index in range(4)]
    engine = _engine(audit_sink=FlakySink())
    with pytest.raises(ConnectionError, match="audit backend unavailable"):
        await engine.process_many(events)
    decisions = await engine.process_many(events)
    reference_engine = _engine()
    reference = [await reference_engine.process(event) for event in events]
    assert [d.intervention.kind for d in decisions] == [d.intervention.kind for d in reference]
    assert [d.duplicate for d in decisions] == [True, True, True, False]


async def test_process_rejects_values_that_are_not_events() -> None:
    with pytest.raises(EventValidationError, match="event must be a BehaviorEvent, not dict"):
        # pyrefly: ignore[bad-argument-type]
        await _engine().process({"scope": "a"})


async def test_expire_scope_releases_only_that_scope() -> None:
    engine = _engine()
    for index in range(2):
        await engine.process(_tool("done", index))
        await engine.process(_tool("live", index))
    assert await engine.expire_scope("done") == 1
    assert await engine.expire_scope("done") == 0
    fresh = await engine.process(_tool("done", 5))
    assert fresh.intervention.kind is InterventionType.NOOP, "history starts over"
    redelivered = await engine.process(_tool("done", 0))
    assert not redelivered.duplicate, "processed event IDs are released too"
    kept = await engine.process(_tool("live", 2))
    assert kept.intervention.kind is InterventionType.NUDGE


@pytest.mark.parametrize("scope", ["", "  ", None, 3])
async def test_expire_scope_rejects_invalid_scopes(scope: object) -> None:
    with pytest.raises(EventValidationError, match="scope must be a non-empty string"):
        # pyrefly: ignore[bad-argument-type]
        await _engine().expire_scope(scope)


async def test_langgraph_store_deletes_a_scope_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_module, "_PAGE", 3)
    backing = InMemoryStore()
    store = LangGraphBehaviorStateStore(backing, namespace=("bw",))
    for index in range(7):
        await store.put(f"k{index}", BehaviorState("p", "gone"))
    await store.put("kept", BehaviorState("p", "kept"))
    # Searches match nested namespaces; their items belong to someone else.
    for index in range(4):
        await backing.aput(("bw", "nested"), f"n{index}", {"scope": "gone"})
    assert await store.delete_scope("gone") == 7
    assert await store.get("kept") == BehaviorState("p", "kept")
    assert len(await backing.asearch(("bw", "nested"))) == 4
    assert await store.delete_scope("gone") == 0


class _Failing(AuditSink):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def write(self, record: AuditRecord) -> None:
        self.calls.append("write")
        raise ConnectionError("write failed")

    async def flush(self) -> None:
        self.calls.append("flush")
        raise ConnectionError("flush failed")

    async def close(self) -> None:
        self.calls.append("close")
        raise ConnectionError("close failed")


async def test_composite_sink_delivers_to_every_sink_and_raises_the_first_failure() -> None:
    failing, second, healthy = _Failing(), _Failing(), InMemoryAuditSink()
    engine = _engine(audit_sink=CompositeAuditSink(failing, healthy, second))
    with pytest.raises(ConnectionError, match="write failed"):
        await engine.process(_tool("a", 0))
    assert len(healthy.records) == 1, "a failing sink does not starve the others"
    with pytest.raises(ConnectionError, match="flush failed"):
        await engine.flush()
    with pytest.raises(ConnectionError, match="close failed"):
        await engine.close()
    assert failing.calls == second.calls == ["write", "flush", "close"]


async def test_composite_sink_with_healthy_sinks() -> None:
    first, second = InMemoryAuditSink(), InMemoryAuditSink()
    composite = CompositeAuditSink(first, second)
    assert composite.sinks == (first, second)
    async with _engine(audit_sink=composite) as engine:
        await engine.process(_tool("a", 0))
        await engine.flush()
    assert first.records == second.records
    assert len(first.records) == 1


def test_composite_sink_rejects_invalid_sinks() -> None:
    with pytest.raises(PolicyConfigurationError, match="at least one sink"):
        CompositeAuditSink()
    with pytest.raises(PolicyConfigurationError, match="not list"):
        # pyrefly: ignore[bad-argument-type]
        CompositeAuditSink(InMemoryAuditSink(), [])
