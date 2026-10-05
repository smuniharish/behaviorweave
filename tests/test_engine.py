from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

import pytest

from behaviorweave import (
    AuditRecord,
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    BehaviorStateStore,
    ConsecutivePattern,
    EventType,
    InMemoryBehaviorStateStore,
    InterventionType,
    Outcome,
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


def _kinds(engine: BehaviorEngine, events: list[BehaviorEvent]) -> list[str]:
    return [engine.process(event).intervention.kind.value for event in events]


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

    def update(self, key: str, fn: Updater) -> BehaviorState:
        self.calls += 1
        if self.calls == self.race_on:
            current = self.get(key)
            assert current is not None
            self.put(key, replace(current, intervention_history=(self.policy_id,)))
        return super().update(key, fn)


class VanishingStore(InMemoryBehaviorStateStore):
    """Deletes the state right before update call ``vanish_on``."""

    def __init__(self, vanish_on: int) -> None:
        super().__init__()
        self.vanish_on = vanish_on
        self.calls = 0

    def update(self, key: str, fn: Updater) -> BehaviorState:
        self.calls += 1
        if self.calls == self.vanish_on:
            self.delete(key)
        return super().update(key, fn)


class KeywordPattern:
    """Custom pattern implementing the protocol directly: counts 'delete' tool calls."""

    pattern_id = "destructive_calls"

    def matches(self, event: BehaviorEvent) -> bool:
        return event.tool_name is not None and "delete" in event.tool_name

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        def apply(current: BehaviorState | None) -> BehaviorState:
            count = (current.count if current else 0) + 1
            return BehaviorState(pattern_id=self.pattern_id, scope=event.scope, count=count)

        state = store.update(f"{event.scope}|{self.pattern_id}", apply)
        return PatternObservation(
            self.pattern_id, event.scope, "delete", "k", state.count, True, state, "deletes"
        )


def test_default_configuration() -> None:
    engine = BehaviorEngine()
    assert engine.patterns == built_in_patterns()
    assert isinstance(engine.store, InMemoryBehaviorStateStore)
    assert engine.rules == ()
    decision = engine.process(_tool())
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
    with pytest.raises(PolicyConfigurationError, match="does not implement"):
        BehaviorEngine(patterns=["nope"])  # type: ignore[list-item]


def test_only_patterns_with_policies_are_evaluated() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 9, InterventionType.NUDGE)],
        state_store=store,
    )
    engine.process(_tool())
    engine.process(BehaviorEvent.outcome_event(Outcome.FAILURE, scope="s"))
    assert {pattern for (_, pattern, _) in store.latest} == {"repeated_tool_call"}


def test_escalation_ladder() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
            PolicyRule("synthesize", "repeated_tool_call", 3, InterventionType.FORCE_SYNTHESIS),
            PolicyRule("stop", "repeated_tool_call", 5, InterventionType.STOP),
        ]
    )
    kinds = _kinds(engine, [_tool(seconds=i) for i in range(6)])
    assert kinds == ["noop", "nudge", "force_synthesis", "force_synthesis", "stop", "stop"]


def test_scopes_are_isolated() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 2, InterventionType.NUDGE)]
    )
    engine.process(BehaviorEvent.tool_call("t", scope="a"))
    assert engine.process(BehaviorEvent.tool_call("t", scope="b")).intervention.kind == "noop"
    assert engine.process(BehaviorEvent.tool_call("t", scope="a")).intervention.kind == "nudge"


def test_once_only_works_without_a_cooldown() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 2, InterventionType.NUDGE, once_only=True)
        ]
    )
    decisions = [engine.process(_tool(seconds=i)) for i in range(5)]
    assert [d.intervention.kind.value for d in decisions] == [
        "noop",
        "nudge",
        "noop",
        "noop",
        "noop",
    ]
    assert [d.suppressed for d in decisions] == [False, False, True, True, True]


def test_cooldown_does_not_suppress_escalation() -> None:
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
    assert _kinds(engine, [_tool(seconds=i) for i in range(5)]) == [
        "noop",
        "nudge",
        "noop",
        "stop",
        "stop",
    ]


def test_cooldown_uses_event_time_and_expires() -> None:
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
    assert _kinds(engine, [_tool(seconds=t) for t in times]) == [
        "noop",
        "nudge",
        "noop",
        "noop",
        "nudge",
        "noop",
    ]


def test_streaks_reset_on_success() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("esc", "failure_streak", 2, InterventionType.ESCALATE)]
    )
    outcomes = [Outcome.FAILURE, Outcome.SUCCESS, Outcome.FAILURE, Outcome.FAILURE]
    events = [BehaviorEvent.outcome_event(o, scope="s") for o in outcomes]
    assert _kinds(engine, events) == ["noop", "noop", "noop", "escalate"]


def test_mixed_retry_signals_form_one_streak() -> None:
    engine = BehaviorEngine(policies=[PolicyRule("r", "retry_streak", 3, InterventionType.NUDGE)])
    events = [
        BehaviorEvent(EventType.RETRY, scope="s"),
        BehaviorEvent.outcome_event(Outcome.RETRY, scope="s"),
        BehaviorEvent.outcome_event(Outcome.FAILURE, scope="s"),
        BehaviorEvent(EventType.RETRY, scope="s", outcome=Outcome.RETRY),
    ]
    assert _kinds(engine, events) == ["noop", "noop", "noop", "nudge"]


def test_redelivery_returns_the_original_decision() -> None:
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
    quiet, review = engine.process(first), engine.process(second)
    assert review.intervention.kind is InterventionType.HUMAN_REVIEW
    replayed = engine.process(second)
    assert replayed == replace(review, duplicate=True), "once-only does not suppress a replay"
    quiet_replay = engine.process(first)
    assert not quiet.actionable
    assert quiet_replay.duplicate
    assert quiet_replay.intervention.kind is InterventionType.NOOP
    later = engine.process(_tool(seconds=2, event_id="e3"))
    assert later.suppressed
    assert engine.process(second) == replace(review, duplicate=True), "survives later events"
    assert store.count("s", "repeated_tool_call") == 3


def test_redelivery_of_a_suppressed_decision_is_a_noop() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True)
        ]
    )
    engine.process(_tool(event_id="e1"))
    suppressed_event = _tool(seconds=1, event_id="e2")
    assert engine.process(suppressed_event).suppressed
    replay = engine.process(suppressed_event)
    assert replay.duplicate
    assert not replay.actionable
    assert replay.explanation is None


def test_replay_ignores_decisions_this_engine_cannot_rebuild() -> None:
    store = InMemoryBehaviorStateStore()
    original = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    event = _tool(event_id="shared")
    assert original.process(event).actionable
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
        replay = engine.process(event)
        assert replay.duplicate
        assert not replay.actionable


def test_recorded_decisions_are_bounded() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    events = [_tool(seconds=i, event_id=f"e{i}") for i in range(300)]
    decisions = [engine.process(event) for event in events]
    state = store.latest[("s", "repeated_tool_call", None)]
    recorded = [entry[0] for entry in state.emissions]
    assert len(recorded) == 256
    assert recorded[0] == "e44"
    assert recorded[-1] == "e299"
    assert engine.process(events[299]) == replace(decisions[299], duplicate=True)


def test_audit_sink_failure_is_recoverable_by_redelivery() -> None:
    failures = iter([OSError("audit backend down")])

    def flaky_sink(record: AuditRecord) -> None:
        error = next(failures, None)
        if error is not None:
            raise error

    engine = BehaviorEngine(
        policies=[
            PolicyRule("halt", "repeated_tool_call", 1, InterventionType.STOP, once_only=True)
        ],
        audit_sink=flaky_sink,
    )
    event = _tool(event_id="e1")
    with pytest.raises(OSError, match="audit backend down"):
        engine.process(event)
    recovered = engine.process(event)
    assert recovered.intervention.kind is InterventionType.STOP
    assert recovered.duplicate


def test_cross_pattern_ranking() -> None:
    def engine(*rules: PolicyRule) -> BehaviorEngine:
        return BehaviorEngine(policies=rules)

    by_priority = engine(
        PolicyRule("nudge", "repeated_tool_call", 1, InterventionType.NUDGE, priority=2),
        PolicyRule("stop", "event_frequency", 1, InterventionType.STOP),
    )
    assert by_priority.process(_tool()).intervention.policy == "nudge"

    by_terminal = engine(
        PolicyRule("nudge", "repeated_tool_call", 1, InterventionType.NUDGE),
        PolicyRule("stop", "event_frequency", 1, InterventionType.STOP),
    )
    assert by_terminal.process(_tool()).intervention.policy == "stop"

    by_count = engine(
        PolicyRule("repeat", "repeated_tool_call", 1, InterventionType.NUDGE),
        PolicyRule("frequent", "event_frequency", 2, InterventionType.WARNING),
    )
    picks = [by_count.process(_tool(n, i)).intervention.policy for i, n in enumerate("aba")]
    assert picks == ["repeat", "repeat", "frequent"]

    suppressed_first = engine(
        PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True),
        PolicyRule("later", "event_frequency", 5, InterventionType.WARNING),
    )
    suppressed_first.process(_tool(seconds=0))
    decision = suppressed_first.process(_tool(seconds=1))
    assert decision.suppressed
    assert decision.intervention.policy == "once"


def test_only_the_returned_decision_is_recorded() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True),
            PolicyRule("stop", "event_frequency", 1, InterventionType.STOP, once_only=True),
        ]
    )
    assert engine.process(_tool(seconds=0)).intervention.policy == "stop"
    assert engine.process(_tool(seconds=1)).intervention.policy == "nudge"


def test_every_returned_decision_is_recorded() -> None:
    store = RecordingStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    engine.process(_tool(seconds=0, event_id="e1"))
    engine.process(_tool(seconds=1, event_id="e2"))
    state = store.latest[("s", "repeated_tool_call", None)]
    assert store.update_calls == 4, "each event: observe, then record the returned decision"
    assert state.intervention_history == ("n",)
    assert state.emissions == (
        ("e1", "n", 1, "'lookup' occurred 1 consecutive time"),
        ("e2", "n", 2, "'lookup' occurred 2 consecutive times"),
    )


def test_concurrent_claim_falls_back_to_suppressed() -> None:
    store = RacingStore("once", race_on=2)
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True)
        ],
        state_store=store,
    )
    decision = engine.process(_tool())
    assert decision.suppressed
    assert not decision.actionable
    assert decision.intervention.reason == "policy 'once' was already applied by a concurrent event"
    assert decision.explanation is not None
    assert decision.explanation.reason == decision.intervention.reason


def test_lost_claim_tries_the_next_candidate() -> None:
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
    assert engine.process(_tool()).intervention.policy == "warn"


def test_commit_recreates_state_deleted_concurrently() -> None:
    store = VanishingStore(vanish_on=2)
    engine = BehaviorEngine(
        policies=[
            PolicyRule("once", "repeated_tool_call", 1, InterventionType.NUDGE, once_only=True)
        ],
        state_store=store,
    )
    assert engine.process(_tool(seconds=0)).actionable
    assert engine.process(_tool(seconds=1)).suppressed


def test_provenance_reference_is_propagated() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)]
    )
    decision = engine.process(_tool(provenance_ref="xai-123"))
    assert decision.explanation is not None
    assert decision.explanation.provenance_ref == "xai-123"
    later = engine.process(_tool(seconds=1)).explanation
    assert later is not None
    assert later.provenance_ref is None


def test_audit_sink_receives_every_decision() -> None:
    records: list[AuditRecord] = []
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 2, InterventionType.NUDGE)],
        audit_sink=records.append,
    )
    first = _tool(seconds=0)
    engine.process(first)
    engine.process(_tool(seconds=1))
    engine.process(BehaviorEvent(EventType.CUSTOM, scope="s"))
    assert [r.decision.intervention.kind.value for r in records] == ["noop", "nudge", "noop"]
    assert records[0].event is first
    assert records[1].pattern == "repeated_tool_call"
    assert records[1].state is not None
    assert records[1].state.count == 2
    assert (records[2].pattern, records[2].state) == (None, None)


def test_custom_patterns_follow_the_protocol() -> None:
    engine = BehaviorEngine(
        patterns=[KeywordPattern()],
        policies=[PolicyRule("review", "destructive_calls", 2, InterventionType.HUMAN_REVIEW)],
    )
    kinds = _kinds(engine, [_tool("delete_user"), _tool("read"), _tool("delete_db")])
    assert kinds == ["noop", "noop", "human_review"]
