"""The extension points: conformance contracts, the LangGraph store, and the sync bridge."""

import asyncio
import contextvars
import threading
from datetime import timedelta

import pytest
from langgraph.store.memory import InMemoryStore

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    BehaviorStateStore,
    EventType,
    InMemoryAuditSink,
    InMemoryBehaviorStateStore,
    InterventionDecision,
    InterventionType,
    Outcome,
    Pattern,
    PolicyConfigurationError,
    PolicyRule,
    _sync,
    built_in_patterns,
)
from behaviorweave._sync import run_sync
from behaviorweave.integrations.langgraph import LangGraphBehaviorStateStore
from behaviorweave.integrations.langgraph import store as store_module
from behaviorweave.testing import BehaviorStateStoreContract, PatternContract

PATTERNS = {pattern.pattern_id: pattern for pattern in built_in_patterns()}


class TestInMemoryStoreContract(BehaviorStateStoreContract):
    async def make_store(self) -> BehaviorStateStore:
        return InMemoryBehaviorStateStore()


class TestLangGraphStoreContract(BehaviorStateStoreContract):
    async def make_store(self) -> BehaviorStateStore:
        return LangGraphBehaviorStateStore(InMemoryStore())


class TestLangGraphStoreOnOneLoop(TestLangGraphStoreContract):
    """``run_scenario`` can be overridden, here to share one event loop."""

    concurrency = 8

    def run_scenario(self, scenario):
        with asyncio.Runner() as runner:
            runner.run(scenario)


def _tool(scope: str, index: int) -> BehaviorEvent:
    return BehaviorEvent.tool_call("search", {"q": "x"}, scope=scope, event_id=f"{scope}:{index}")


def _outcome(outcome: Outcome):
    def make(scope: str, index: int) -> BehaviorEvent:
        return BehaviorEvent.outcome_event(outcome, scope=scope, event_id=f"{scope}:{index}")

    return make


def _node(scope: str, index: int) -> BehaviorEvent:
    return BehaviorEvent(
        EventType.NODE_EXECUTION, scope, event_id=f"{scope}:{index}", node_name="n"
    )


def _delegation(scope: str, index: int) -> BehaviorEvent:
    return BehaviorEvent(
        EventType.DELEGATION, scope, event_id=f"{scope}:{index}", agent_name="a", target_agent="b"
    )


def _bounce(scope: str, index: int) -> BehaviorEvent:
    source, target = ("a", "b") if index % 2 == 0 else ("b", "a")
    return BehaviorEvent(
        EventType.AGENT_HANDOFF,
        scope,
        event_id=f"{scope}:{index}",
        agent_name=source,
        target_agent=target,
    )


EVENTS = {
    "repeated_tool_call": _tool,
    "repeated_node_execution": _node,
    "failure_streak": _outcome(Outcome.FAILURE),
    "retry_streak": _outcome(Outcome.RETRY),
    "success_streak": _outcome(Outcome.SUCCESS),
    "delegation_streak": _delegation,
    "oscillation": _bounce,
    "event_frequency": _tool,
}


def test_every_built_in_pattern_has_a_contract() -> None:
    assert set(EVENTS) == set(PATTERNS)


def _contract(pattern_id: str) -> type[PatternContract]:
    def make_pattern(self: PatternContract) -> Pattern:
        return PATTERNS[pattern_id]

    def make_event(self: PatternContract, scope: str, index: int) -> BehaviorEvent:
        return EVENTS[pattern_id](scope, index)

    return type(
        f"Test{pattern_id.title().replace('_', '')}Contract",
        (PatternContract,),
        {"make_pattern": make_pattern, "make_event": make_event},
    )


for _pattern_id in EVENTS:
    _cls = _contract(_pattern_id)
    globals()[_cls.__name__] = _cls


class TestPatternContractOnLangGraphStore(PatternContract):
    def make_pattern(self) -> Pattern:
        return PATTERNS["failure_streak"]

    def make_event(self, scope: str, index: int) -> BehaviorEvent:
        return _outcome(Outcome.FAILURE)(scope, index)

    async def make_store(self) -> BehaviorStateStore:
        return LangGraphBehaviorStateStore(InMemoryStore(), namespace=("tests",))


class LooseStore(BehaviorStateStore):
    """Violates the contract: no validation, and updates are not atomic."""

    def __init__(self) -> None:
        self.states: dict[str, object] = {}

    async def get(self, key: str) -> BehaviorState | None:
        # pyrefly: ignore[bad-return]
        return self.states.get(key)

    async def update(self, key, fn):
        current = await self.get(key)
        await asyncio.sleep(0)
        state = fn(current)
        self.states[key] = state
        return state

    async def put(self, key: str, state: BehaviorState) -> None:
        self.states[key] = state

    async def delete(self, key: str) -> None:
        self.states.pop(key, None)

    async def delete_scope(self, scope: str) -> int:
        return 0


@pytest.mark.parametrize(
    ("test", "message"),
    [
        ("test_concurrent_updates_of_one_key_are_serialized", "after concurrent updates"),
        ("test_delete_scope_removes_only_that_scope", "expected 2 removed states"),
        ("test_put_rejects_a_value_that_is_not_a_state", "put accepted a value"),
        ("test_update_rejects_a_result_that_is_not_a_state", "update accepted a result"),
    ],
)
def test_contracts_report_violations(test: str, message: str) -> None:
    class Loose(BehaviorStateStoreContract):
        async def make_store(self) -> BehaviorStateStore:
            return LooseStore()

    with pytest.raises(AssertionError, match=message):
        getattr(Loose(), test)()


async def test_langgraph_store_uses_its_namespace_and_ttl() -> None:
    backing = InMemoryStore()
    store = LangGraphBehaviorStateStore(backing, namespace=("tenant-1", "behavior"))
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 2, InterventionType.NUDGE)],
        state_store=store,
    )
    async with engine:
        await engine.process(_tool("s", 0))
        decision = await engine.process(_tool("s", 1))
    assert decision.intervention.kind is InterventionType.NUDGE
    items = await backing.asearch(("tenant-1", "behavior"))
    assert items
    assert all(isinstance(BehaviorState.from_dict(item.value), BehaviorState) for item in items)

    expiring = ExpiringStore()
    timed = LangGraphBehaviorStateStore(expiring, ttl=timedelta(minutes=5))
    await timed.put("k", BehaviorState(pattern_id="p", scope="s"))
    await timed.update("k", lambda state: state or BehaviorState(pattern_id="p", scope="s"))
    assert await timed.get("k") == BehaviorState(pattern_id="p", scope="s")
    assert expiring.ttls == [5.0, 5.0], "every write refreshes the TTL, in minutes"


class ExpiringStore(InMemoryStore):
    """An in-memory store that accepts TTLs and records them."""

    supports_ttl = True

    def __init__(self) -> None:
        super().__init__()
        self.ttls: list[float | None] = []

    async def aput(self, namespace, key, value, index=None, *, ttl=None):
        self.ttls.append(ttl)
        await super().aput(namespace, key, value, index)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"store": {}}, "store must be a langgraph BaseStore, not dict"),
        ({"namespace": ()}, "namespace must be a non-empty tuple"),
        ({"namespace": ("a.b",)}, "namespace must be a non-empty tuple"),
        ({"namespace": ("",)}, "namespace must be a non-empty tuple"),
        ({"namespace": (1,)}, "namespace must be a non-empty tuple"),
        ({"ttl": timedelta(0)}, "ttl must be a positive timedelta"),
        ({"ttl": timedelta(minutes=1)}, "InMemoryStore does not support TTL"),
    ],
)
def test_langgraph_store_rejects_invalid_configuration(
    kwargs: dict[str, object], message: str
) -> None:
    options = {"store": InMemoryStore(), **kwargs}
    with pytest.raises(PolicyConfigurationError, match=message):
        # pyrefly: ignore[bad-argument-type]
        LangGraphBehaviorStateStore(**options)


async def test_langgraph_store_updates_wait_for_a_contended_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_module, "_STRIPES", 1)
    store = LangGraphBehaviorStateStore(InMemoryStore())
    lock = store._locks[0]
    lock.acquire()
    waiting = asyncio.ensure_future(store.update("k", lambda _: BehaviorState("p", "s")))
    await asyncio.sleep(0.05)
    assert not waiting.done(), "the update waits for the held lock"
    lock.release()
    assert (await waiting).pattern_id == "p"
    assert not lock.locked()


async def test_a_cancelled_waiter_releases_the_lock_it_acquires() -> None:
    store = LangGraphBehaviorStateStore(InMemoryStore())
    lock = store._locks[0]
    lock.acquire()
    acquired = threading.Event()
    waiter = asyncio.ensure_future(store_module._acquire(lock))
    await asyncio.sleep(0.05)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    lock.release()  # the background acquisition now succeeds, then releases the lock
    for _ in range(100):
        await asyncio.sleep(0.01)
        if lock.acquire(blocking=False):
            acquired.set()
            lock.release()
            break
    assert acquired.is_set(), "the cancelled waiter must not keep the lock"


def test_run_sync_without_a_running_loop_reuses_the_thread_loop() -> None:
    marker: contextvars.ContextVar[str] = contextvars.ContextVar("marker")
    marker.set("caller")

    async def loop_and_marker() -> tuple[asyncio.AbstractEventLoop, str]:
        return asyncio.get_running_loop(), marker.get()

    first, seen = run_sync(loop_and_marker())
    second, _ = run_sync(loop_and_marker())
    assert first is second, "one event loop is reused per thread"
    assert seen == "caller", "the caller's context is propagated"


async def test_run_sync_inside_a_running_loop_uses_a_helper_loop() -> None:
    marker: contextvars.ContextVar[str] = contextvars.ContextVar("marker")
    marker.set("async-caller")
    current = asyncio.get_running_loop()

    async def loop_and_marker() -> tuple[asyncio.AbstractEventLoop, str]:
        return asyncio.get_running_loop(), marker.get()

    helper, seen = run_sync(loop_and_marker())
    again, _ = run_sync(loop_and_marker())
    assert helper is not current
    assert helper is again, "the helper loop is reused by later calls"
    assert seen == "async-caller"


def test_thread_loops_close_their_idle_loop() -> None:
    holder = _sync._ThreadLoop()
    holder.__del__()
    assert holder.loop.is_closed()
    holder.__del__()  # an already closed loop is left alone


def test_run_sync_propagates_exceptions() -> None:
    async def fail() -> None:
        raise LookupError("missing")

    with pytest.raises(LookupError, match="missing"):
        run_sync(fail())


def test_run_sync_helper_and_thread_loops_are_released() -> None:
    def worker() -> None:
        async def nested() -> asyncio.AbstractEventLoop:
            async def inner() -> asyncio.AbstractEventLoop:
                return asyncio.get_running_loop()

            return run_sync(inner())

        run_sync(nested())

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()


async def test_decisions_round_trip_through_dicts() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "n",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                message="Reuse it.",
            )
        ]
    )
    await engine.process(_tool("s", 0))
    decision = await engine.process(_tool("s", 1))
    restored = InterventionDecision.from_dict(decision.to_dict())
    assert restored == decision
    noop = await engine.process(BehaviorEvent.outcome_event(Outcome.SUCCESS, scope="s"))
    assert InterventionDecision.from_dict(noop.to_dict()) == noop
    unbounded = decision.to_dict()
    # pyrefly: ignore[unsupported-operation]
    unbounded["explanation"]["threshold"] = None
    explanation = InterventionDecision.from_dict(unbounded).explanation
    assert explanation is not None
    assert explanation.threshold is None


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"intervention": {}},
        {"intervention": {"kind": "nudge"}, "explanation": {"pattern": "p"}},
        {"intervention": None},
    ],
)
def test_malformed_decisions_are_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="invalid intervention decision"):
        InterventionDecision.from_dict(data)


async def test_in_memory_audit_sink_records_and_clears() -> None:
    sink = InMemoryAuditSink()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        audit_sink=sink,
    )
    await engine.process(_tool("s", 0))
    assert [record.decision.intervention.kind for record in sink.records] == [
        InterventionType.NUDGE
    ]
    await sink.clear()
    assert sink.records == ()
