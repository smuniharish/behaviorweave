from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

import pytest

from behaviorweave import (
    AuditRecord,
    AuditSink,
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    BehaviorStateStore,
    ConsecutivePattern,
    EventType,
    InMemoryAuditSink,
    InMemoryBehaviorStateStore,
    InterventionType,
    Outcome,
    Pattern,
    PatternObservation,
    PolicyConfigurationError,
    PolicyRule,
    built_in_patterns,
)
from support import RecordingStore, at

Updater = Callable[[BehaviorState | None], BehaviorState]


def _tool(
    name: str = "lookup",
    seconds: float = 0,
    *,
    event_id: str | None = None,
    provenance_ref: str | None = None,
) -> BehaviorEvent:
    return BehaviorEvent.tool_call(
        name, scope="s", timestamp=at(seconds), event_id=event_id, provenance_ref=provenance_ref
    )


async def _kinds(engine: BehaviorEngine, events: list[BehaviorEvent]) -> list[str]:
    return [(await engine.process(event)).intervention.kind.value for event in events]


class FalsyStore(InMemoryBehaviorStateStore):
    def __len__(self) -> int:
        return 0


class RacingStore(InMemoryBehaviorStateStore):
    """Simulates another thread claiming ``policy_id`` just before update call ``race_on``."""

    def __init__(self, policy_id: str, race_on: int) -> None:
        super().__init__()
        self.policy_id = policy_id
        self.race_on = race_on
        self.calls = 0

    async def update(self, key: str, fn: Updater) -> BehaviorState:
        self.calls += 1
        if self.calls == self.race_on:
            current = await self.get(key)
            assert current is not None
            await self.put(key, replace(current, intervention_history=(self.policy_id,)))
        return await super().update(key, fn)


class VanishingStore(InMemoryBehaviorStateStore):
    """Deletes the state right before update call ``vanish_on``."""

    def __init__(self, vanish_on: int) -> None:
        super().__init__()
        self.vanish_on = vanish_on
        self.calls = 0

    async def update(self, key: str, fn: Updater) -> BehaviorState:
        self.calls += 1
        if self.calls == self.vanish_on:
            await self.delete(key)
        return await super().update(key, fn)


class KeywordPattern(Pattern):
    """Custom pattern subclassing the ABC directly: counts 'delete' tool calls."""

    pattern_id = "destructive_calls"

    def matches(self, event: BehaviorEvent) -> bool:
        return event.tool_name is not None and "delete" in event.tool_name

    async def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        def apply(current: BehaviorState | None) -> BehaviorState:
            count = (current.count if current else 0) + 1
            return BehaviorState(pattern_id=self.pattern_id, scope=event.scope, count=count)

        state = await store.update(f"{event.scope}|{self.pattern_id}", apply)
        return PatternObservation(
            self.pattern_id, event.scope, "delete", "k", state.count, True, state, "deletes"
        )


async def test_default_configuration() -> None:
    engine = BehaviorEngine()
    assert engine.patterns == built_in_patterns()
    assert isinstance(engine.store, InMemoryBehaviorStateStore)
    assert engine.rules == ()
    decision = await engine.process(_tool())
    assert decision.intervention.kind is InterventionType.NOOP
    assert decision.intervention.scope == "s"


def test_empty_pattern_collection_means_no_patterns() -> None:
    engine = BehaviorEngine(patterns=[])
    assert engine.patterns == ()
    with pytest.raises(PolicyConfigurationError, match="unknown pattern"):
        BehaviorEngine(
            patterns=[], policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)]
        )


def test_falsy_custom_store_is_honored() -> None:
    store = FalsyStore()
    assert BehaviorEngine(state_store=store).store is store


def test_configuration_errors() -> None:
    with pytest.raises(PolicyConfigurationError, match="unknown pattern"):
        BehaviorEngine(policies=[PolicyRule("n", "repeated_tool_calls", 1, InterventionType.NUDGE)])
    duplicate = ConsecutivePattern("dup", frozenset({EventType.TOOL_CALL}))
    with pytest.raises(PolicyConfigurationError, match="duplicate pattern_id"):
        BehaviorEngine(patterns=[duplicate, duplicate])
    with pytest.raises(PolicyConfigurationError, match="is not a Pattern"):
        # pyrefly: ignore[bad-argument-type]
        BehaviorEngine(patterns=["nope"])
    with pytest.raises(PolicyConfigurationError, match="state_store must be"):
        # pyrefly: ignore[bad-argument-type]
        BehaviorEngine(state_store={})
    with pytest.raises(PolicyConfigurationError, match="audit_sink must be"):
        # pyrefly: ignore[bad-argument-type]
        BehaviorEngine(audit_sink=print)

    class Unnamed(KeywordPattern):
        pattern_id = " "

    with pytest.raises(PolicyConfigurationError, match="non-empty string"):
        BehaviorEngine(patterns=[Unnamed()])


def test_patterns_and_stores_must_implement_the_abc() -> None:
    class Partial(Pattern):
        pattern_id = "partial"

        def matches(self, event: BehaviorEvent) -> bool:
            return True

    class PartialStore(BehaviorStateStore):
        async def get(self, key: str) -> BehaviorState | None:
            return None

    with pytest.raises(TypeError, match="abstract"):
        # pyrefly: ignore[bad-instantiation]
        Partial()
    with pytest.raises(TypeError, match="abstract"):
        # pyrefly: ignore[bad-instantiation]
        PartialStore()


class _ClosingSink(AuditSink):
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.events: list[str] = []

    async def write(self, record: AuditRecord) -> None:
        self.events.append("write")

    async def flush(self) -> None:
        self.events.append("flush")

    async def close(self) -> None:
        self.events.append("close")
        if self.error is not None:
            raise self.error


class _ClosingStore(InMemoryBehaviorStateStore):
    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self.error = error
        self.closed = False

    async def close(self) -> None:
        self.closed = True
        if self.error is not None:
            raise self.error


async def test_engine_is_an_async_context_manager_that_flushes_and_closes() -> None:
    sink, store = _ClosingSink(), _ClosingStore()
    async with BehaviorEngine(audit_sink=sink, state_store=store) as engine:
        await engine.process(_tool())
        await engine.flush()
    assert sink.events == ["write", "flush", "close"]
    assert store.closed
    async with BehaviorEngine() as plain:
        await plain.flush()


async def test_close_attempts_every_component_and_raises_the_first_failure() -> None:
    sink, store = _ClosingSink(OSError("sink")), _ClosingStore(OSError("store"))
    with pytest.raises(OSError, match="sink"):
        await BehaviorEngine(audit_sink=sink, state_store=store).close()
    assert store.closed
    with pytest.raises(OSError, match="store"):
        await BehaviorEngine(
            audit_sink=_ClosingSink(), state_store=_ClosingStore(OSError("store"))
        ).close()


async def test_only_patterns_with_policies_are_evaluated() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 9, InterventionType.NUDGE)],
        state_store=store,
    )
    await engine.process(_tool())
    await engine.process(BehaviorEvent.outcome_event(Outcome.FAILURE, scope="s"))
    assert {pattern for (_, pattern, _) in store.latest} == {"repeated_tool_call"}


async def test_escalation_ladder() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
            PolicyRule("synthesize", "repeated_tool_call", 3, InterventionType.FORCE_SYNTHESIS),
            PolicyRule("stop", "repeated_tool_call", 5, InterventionType.STOP),
        ]
    )
    kinds = await _kinds(engine, [_tool(seconds=i) for i in range(6)])
    assert kinds == ["noop", "nudge", "force_synthesis", "force_synthesis", "stop", "stop"]


async def test_scopes_are_isolated() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 2, InterventionType.NUDGE)]
    )
    await engine.process(BehaviorEvent.tool_call("t", scope="a"))
    assert (
        await engine.process(BehaviorEvent.tool_call("t", scope="b"))
    ).intervention.kind == "noop"
    assert (
        await engine.process(BehaviorEvent.tool_call("t", scope="a"))
    ).intervention.kind == "nudge"


async def test_once_only_works_without_a_cooldown() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 2, InterventionType.NUDGE, once_only=True)
        ]
    )
    decisions = [await engine.process(_tool(seconds=i)) for i in range(5)]
    assert [d.intervention.kind.value for d in decisions] == [
        "noop",
        "nudge",
        "noop",
        "noop",
        "noop",
    ]
    assert [d.suppressed for d in decisions] == [False, False, True, True, True]


async def test_cooldown_does_not_suppress_escalation() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "nudge",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                cooldown=timedelta(hours=1),
            ),
            PolicyRule("stop", "repeated_tool_call", 4, InterventionType.STOP),
        ]
    )
    assert await _kinds(engine, [_tool(seconds=i) for i in range(5)]) == [
        "noop",
        "nudge",
        "noop",
        "stop",
        "stop",
    ]


async def test_cooldown_uses_event_time_and_expires() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "nudge",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                cooldown=timedelta(seconds=10),
            )
        ]
    )
    times = [0, 1, 5, 10, 11, 12]
    assert await _kinds(engine, [_tool(seconds=t) for t in times]) == [
        "noop",
        "nudge",
        "noop",
        "noop",
        "nudge",
        "noop",
    ]


async def test_streaks_reset_on_success() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("esc", "failure_streak", 2, InterventionType.ESCALATE)]
    )
    outcomes = [Outcome.FAILURE, Outcome.SUCCESS, Outcome.FAILURE, Outcome.FAILURE]
    events = [BehaviorEvent.outcome_event(o, scope="s") for o in outcomes]
    assert await _kinds(engine, events) == ["noop", "noop", "noop", "escalate"]


async def test_mixed_retry_signals_form_one_streak() -> None:
    engine = BehaviorEngine(policies=[PolicyRule("r", "retry_streak", 3, InterventionType.NUDGE)])
    events = [
        BehaviorEvent(EventType.RETRY, scope="s"),
        BehaviorEvent.outcome_event(Outcome.RETRY, scope="s"),
        BehaviorEvent.outcome_event(Outcome.FAILURE, scope="s"),
        BehaviorEvent(EventType.RETRY, scope="s", outcome=Outcome.RETRY),
    ]
    assert await _kinds(engine, events) == ["noop", "noop", "noop", "nudge"]


async def test_redelivery_returns_the_original_decision() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "review", "repeated_tool_call", 2, InterventionType.HUMAN_REVIEW, once_only=True
            )
        ],
        state_store=store,
    )
    first, second = _tool(event_id="e1"), _tool(seconds=1, event_id="e2")
    quiet, review = await engine.process(first), await engine.process(second)
    assert review.intervention.kind is InterventionType.HUMAN_REVIEW
    replayed = await engine.process(second)
    assert replayed == replace(review, duplicate=True), "once-only does not suppress a replay"
    quiet_replay = await engine.process(first)
    assert not quiet.actionable
    assert quiet_replay.duplicate
    assert quiet_replay.intervention.kind is InterventionType.NOOP
    later = await engine.process(_tool(seconds=2, event_id="e3"))
    assert later.suppressed
    assert await engine.process(second) == replace(review, duplicate=True), "survives later events"
    assert store.count("s", "repeated_tool_call") == 3


async def test_redelivery_of_a_suppressed_decision_is_a_noop() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True)
        ]
    )
    await engine.process(_tool(event_id="e1"))
    suppressed_event = _tool(seconds=1, event_id="e2")
    assert (await engine.process(suppressed_event)).suppressed
    replay = await engine.process(suppressed_event)
    assert replay.duplicate
    assert not replay.actionable
    assert replay.explanation is None


async def test_replay_ignores_decisions_this_engine_cannot_rebuild() -> None:
    store = InMemoryBehaviorStateStore()
    original = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    event = _tool(event_id="shared")
    assert (await original.process(event)).actionable
    unknown_policy = BehaviorEngine(
        policies=[PolicyRule("other", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    other_pattern = BehaviorEngine(
        policies=[
            PolicyRule("n", "event_frequency", 99, InterventionType.NUDGE),
            PolicyRule("m", "repeated_tool_call", 99, InterventionType.NUDGE),
        ],
        state_store=store,
    )
    for engine in (unknown_policy, other_pattern):
        replay = await engine.process(event)
        assert replay.duplicate
        assert not replay.actionable


async def test_recorded_decisions_are_bounded() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    events = [_tool(seconds=i, event_id=f"e{i}") for i in range(300)]
    decisions = [await engine.process(event) for event in events]
    state = store.latest[("s", "repeated_tool_call", None)]
    recorded = [entry[0] for entry in state.emissions]
    assert len(recorded) == 256
    assert recorded[0] == "e44"
    assert recorded[-1] == "e299"
    assert await engine.process(events[299]) == replace(decisions[299], duplicate=True)


async def test_audit_sink_failure_is_recoverable_by_redelivery() -> None:
    failures = iter([OSError("audit backend down")])

    class FlakySink(AuditSink):
        async def write(self, record: AuditRecord) -> None:
            error = next(failures, None)
            if error is not None:
                raise error

    engine = BehaviorEngine(
        policies=[
            PolicyRule("halt", "repeated_tool_call", 1, InterventionType.STOP, once_only=True)
        ],
        audit_sink=FlakySink(),
    )
    event = _tool(event_id="e1")
    with pytest.raises(OSError, match="audit backend down"):
        await engine.process(event)
    recovered = await engine.process(event)
    assert recovered.intervention.kind is InterventionType.STOP
    assert recovered.duplicate


async def test_cross_pattern_ranking() -> None:
    def engine(*rules: PolicyRule) -> BehaviorEngine:
        return BehaviorEngine(policies=rules)

    by_priority = engine(
        PolicyRule("nudge", "repeated_tool_call", 1, InterventionType.NUDGE, priority=2),
        PolicyRule("stop", "event_frequency", 1, InterventionType.STOP),
    )
    assert (await by_priority.process(_tool())).intervention.policy == "nudge"

    by_terminal = engine(
        PolicyRule("nudge", "repeated_tool_call", 1, InterventionType.NUDGE),
        PolicyRule("stop", "event_frequency", 1, InterventionType.STOP),
    )
    assert (await by_terminal.process(_tool())).intervention.policy == "stop"

    by_count = engine(
        PolicyRule("repeat", "repeated_tool_call", 1, InterventionType.NUDGE),
        PolicyRule("frequent", "event_frequency", 2, InterventionType.WARNING),
    )
    picks = [(await by_count.process(_tool(n, i))).intervention.policy for i, n in enumerate("aba")]
    assert picks == ["repeat", "repeat", "frequent"]

    suppressed_first = engine(
        PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True),
        PolicyRule("later", "event_frequency", 5, InterventionType.WARNING),
    )
    await suppressed_first.process(_tool(seconds=0))
    decision = await suppressed_first.process(_tool(seconds=1))
    assert decision.suppressed
    assert decision.intervention.policy == "once"


async def test_only_the_returned_decision_is_recorded() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True),
            PolicyRule("stop", "event_frequency", 1, InterventionType.STOP, once_only=True),
        ]
    )
    assert (await engine.process(_tool(seconds=0))).intervention.policy == "stop"
    assert (await engine.process(_tool(seconds=1))).intervention.policy == "nudge"


async def test_every_returned_decision_is_recorded() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    await engine.process(_tool(seconds=0, event_id="e1"))
    await engine.process(_tool(seconds=1, event_id="e2"))
    state = store.latest[("s", "repeated_tool_call", None)]
    assert store.update_calls == 4, "each event: observe, then record the returned decision"
    assert state.intervention_history == ("n",)
    assert state.emissions == (
        ("e1", "n", 1, "'lookup' occurred 1 consecutive time"),
        ("e2", "n", 2, "'lookup' occurred 2 consecutive times"),
    )


async def test_concurrent_claim_falls_back_to_suppressed() -> None:
    store = RacingStore("once", race_on=2)
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True)
        ],
        state_store=store,
    )
    decision = await engine.process(_tool())
    assert decision.suppressed
    assert not decision.actionable
    assert decision.intervention.reason == "policy 'once' was already applied by a concurrent event"
    assert decision.explanation is not None
    assert decision.explanation.reason == decision.intervention.reason


async def test_lost_claim_tries_the_next_candidate() -> None:
    store = RacingStore("once", race_on=3)
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True, priority=1
            ),
            PolicyRule("warn", "event_frequency", 1, InterventionType.WARNING),
        ],
        state_store=store,
    )
    assert (await engine.process(_tool())).intervention.policy == "warn"


async def test_commit_recreates_state_deleted_concurrently() -> None:
    store = VanishingStore(vanish_on=2)
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True)
        ],
        state_store=store,
    )
    assert (await engine.process(_tool(seconds=0))).actionable
    assert (await engine.process(_tool(seconds=1))).suppressed


async def test_provenance_reference_is_propagated() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)]
    )
    decision = await engine.process(_tool(provenance_ref="xai-123"))
    assert decision.explanation is not None
    assert decision.explanation.provenance_ref == "xai-123"
    later = (await engine.process(_tool(seconds=1))).explanation
    assert later is not None
    assert later.provenance_ref is None


async def test_audit_sink_receives_every_decision() -> None:
    sink = InMemoryAuditSink()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 2, InterventionType.NUDGE)],
        audit_sink=sink,
    )
    first = _tool(seconds=0)
    await engine.process(first)
    await engine.process(_tool(seconds=1))
    await engine.process(BehaviorEvent(EventType.CUSTOM, scope="s"))
    records = sink.records
    assert [r.decision.intervention.kind.value for r in records] == ["noop", "nudge", "noop"]
    assert records[0].event is first
    assert records[1].pattern == "repeated_tool_call"
    assert records[1].state is not None
    assert records[1].state.count == 2
    assert (records[2].pattern, records[2].state) == (None, None)


async def test_custom_patterns_subclass_the_abc() -> None:
    engine = BehaviorEngine(
        patterns=[KeywordPattern()],
        policies=[PolicyRule("review", "destructive_calls", 2, InterventionType.HUMAN_REVIEW)],
    )
    kinds = await _kinds(engine, [_tool("delete_user"), _tool("read"), _tool("delete_db")])
    assert kinds == ["noop", "noop", "human_review"]
