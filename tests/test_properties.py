"""Property-based tests: BehaviorWeave semantics checked against simple reference models."""

import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, timedelta
from random import Random
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    ConsecutivePattern,
    EventType,
    FrequencyPattern,
    InMemoryBehaviorStateStore,
    InterventionType,
    OscillationPattern,
    Outcome,
    PatternObservation,
    PolicyEngine,
    PolicyRule,
    StreakPattern,
    built_in_patterns,
)
from behaviorweave._util import canonical, dumps
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter
from support import RecordingStore, at

json_scalars = st.none() | st.booleans() | st.integers() | st.text(max_size=8)
json_values = st.recursive(
    json_scalars | st.floats(allow_nan=False, allow_infinity=False),
    lambda inner: (
        st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=5), inner, max_size=3)
    ),
    max_leaves=12,
)
argument_dicts = st.dictionaries(st.text(max_size=6), json_values, max_size=5)
any_values = st.recursive(
    json_scalars
    | st.floats()
    | st.datetimes(timezones=st.just(UTC))
    | st.dates()
    | st.binary(max_size=4),
    lambda inner: (
        st.lists(inner, max_size=3)
        | st.tuples(inner, inner)
        | st.frozensets(json_scalars, max_size=3)
        | st.dictionaries(st.integers() | st.text(max_size=3), inner, max_size=3)
    ),
    max_leaves=10,
)
names = st.sampled_from(["a", "b", "c"])
outcomes = st.sampled_from(list(Outcome))
interventions = st.sampled_from([t for t in InterventionType if t is not InterventionType.NOOP])


@given(argument_dicts, st.randoms())
def test_fingerprint_ignores_key_order(arguments: dict[str, object], rng: Random) -> None:
    items = list(arguments.items())
    rng.shuffle(items)
    original = BehaviorEvent.tool_call("tool", arguments, scope="s").fingerprint
    assert BehaviorEvent.tool_call("tool", dict(items), scope="s").fingerprint == original


@given(argument_dicts, argument_dicts)
def test_fingerprint_distinguishes_different_arguments(first: dict, second: dict) -> None:
    same_canonical = dumps(canonical(first)) == dumps(canonical(second))
    same_fingerprint = (
        BehaviorEvent.tool_call("tool", first, scope="s").fingerprint
        == BehaviorEvent.tool_call("tool", second, scope="s").fingerprint
    )
    assert same_canonical == same_fingerprint


@given(st.dictionaries(st.text(max_size=4), any_values, max_size=4))
def test_fingerprinting_and_serialization_are_total(arguments: dict) -> None:
    event = BehaviorEvent.tool_call("tool", arguments, scope="s", metadata={"extra": arguments})
    assert event.fingerprint is not None
    assert json.loads(event.to_json())["tool_name"] == "tool"


@given(st.lists(names, max_size=60))
def test_consecutive_count_is_the_trailing_run_length(sequence: list[str]) -> None:
    store = InMemoryBehaviorStateStore()
    pattern = ConsecutivePattern("p", frozenset({EventType.NODE_EXECUTION}))
    run, previous = 0, None
    for name in sequence:
        event = BehaviorEvent(EventType.NODE_EXECUTION, scope="s", node_name=name)
        run, previous = (run + 1 if name == previous else 1), name
        assert pattern.observe(event, store).count == run


@given(st.lists(outcomes, max_size=60))
def test_streaks_follow_the_reference_model(sequence: list[Outcome]) -> None:
    streaks = [p for p in built_in_patterns() if isinstance(p, StreakPattern)]
    store = InMemoryBehaviorStateStore()
    model = dict.fromkeys((p.pattern_id for p in streaks), 0)
    for outcome in sequence:
        event = BehaviorEvent.outcome_event(outcome, scope="s")
        for pattern in streaks:
            if outcome in pattern.counts:
                model[pattern.pattern_id] += 1
            elif outcome in pattern.resets:
                model[pattern.pattern_id] = 0
            if pattern.matches(event):
                assert pattern.observe(event, store).count == model[pattern.pattern_id]


@given(st.lists(names, max_size=60))
def test_oscillation_follows_the_reference_model(sequence: list[str]) -> None:
    store = InMemoryBehaviorStateStore()
    pattern = OscillationPattern("p", frozenset({EventType.NODE_EXECUTION}))
    before_previous, previous, count = None, None, 0
    for name in sequence:
        event = BehaviorEvent(EventType.NODE_EXECUTION, scope="s", node_name=name)
        count = count + 1 if name == before_previous and name != previous else 0
        before_previous, previous = previous, name
        assert pattern.observe(event, store).count == count


@given(st.lists(names, max_size=60))
def test_frequency_counts_every_occurrence(sequence: list[str]) -> None:
    store = InMemoryBehaviorStateStore()
    pattern = FrequencyPattern("p", frozenset({EventType.NODE_EXECUTION}))
    seen: Counter[str] = Counter()
    for name in sequence:
        seen[name] += 1
        event = BehaviorEvent(EventType.NODE_EXECUTION, scope="s", node_name=name)
        assert pattern.observe(event, store).count == seen[name]


def _event_stream(draw_names: list[str], draw_outcomes: list[Outcome]) -> list[BehaviorEvent]:
    events: list[BehaviorEvent] = []
    for index, (name, outcome) in enumerate(zip(draw_names, draw_outcomes, strict=False)):
        events.append(BehaviorEvent.tool_call(name, scope="s", timestamp=at(index)))
        events.append(BehaviorEvent.outcome_event(outcome, scope="s", timestamp=at(index)))
        events.append(
            BehaviorEvent(
                EventType.AGENT_HANDOFF,
                scope="s",
                agent_name="lead",
                target_agent=name,
                timestamp=at(index),
            )
        )
    return events


ALL_PATTERN_POLICIES = [
    PolicyRule(f"rule-{p.pattern_id}", p.pattern_id, 2, InterventionType.NUDGE)
    for p in built_in_patterns()
]


@given(st.lists(names, max_size=15), st.lists(outcomes, max_size=15), st.data())
def test_redelivery_repeats_the_original_decision_without_changing_state(
    name_list: list[str], outcome_list: list[Outcome], data: st.DataObject
) -> None:
    events = _event_stream(name_list, outcome_list)
    with_replays: list[BehaviorEvent] = []
    for index, event in enumerate(events):
        with_replays.append(event)
        if data.draw(st.booleans()):
            with_replays.append(events[data.draw(st.integers(0, index))])
    plain_store, replay_store = RecordingStore(), RecordingStore()
    plain = BehaviorEngine(policies=ALL_PATTERN_POLICIES, state_store=plain_store)
    replayed = BehaviorEngine(policies=ALL_PATTERN_POLICIES, state_store=replay_store)
    expected = {event.event_id: plain.process(event) for event in events}
    seen: set[str] = set()
    for event in with_replays:
        decision = replayed.process(event)
        original = expected[event.event_id]
        if event.event_id not in seen:
            assert decision == original
        elif original.actionable:
            assert decision == replace(original, duplicate=True)
        else:
            assert decision.duplicate
            assert not decision.actionable
        seen.add(event.event_id)
    assert replay_store.latest == plain_store.latest


@given(st.lists(st.tuples(st.sampled_from(["s1", "s2", "s3"]), names), max_size=40))
def test_scopes_never_influence_each_other(steps: list[tuple[str, str]]) -> None:
    rules = [
        PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
        PolicyRule(
            "cool", "event_frequency", 3, InterventionType.WARNING, cooldown=timedelta(seconds=5)
        ),
    ]
    events = [
        BehaviorEvent.tool_call(name, scope=scope, timestamp=at(i))
        for i, (scope, name) in enumerate(steps)
    ]
    shared = BehaviorEngine(policies=rules)
    interleaved = [(e.scope, shared.process(e).intervention.kind) for e in events]
    for scope in {"s1", "s2", "s3"}:
        isolated = BehaviorEngine(policies=rules)
        expected = [isolated.process(e).intervention.kind for e in events if e.scope == scope]
        assert [kind for s, kind in interleaved if s == scope] == expected


@st.composite
def rule_sets(draw: st.DrawFn) -> list[PolicyRule]:
    size = draw(st.integers(1, 6))
    return [
        PolicyRule(
            f"r{i}",
            "p",
            draw(st.integers(1, 5)),
            draw(interventions),
            priority=draw(st.integers(-2, 2)),
        )
        for i in range(size)
    ]


@given(rule_sets(), st.integers(0, 7))
def test_policy_selection_matches_the_precedence_oracle(
    rules: list[PolicyRule], count: int
) -> None:
    state = BehaviorState(pattern_id="p", scope="s", count=count, last_seen=at(0))
    observation = PatternObservation("p", "s", "fp", "k", count, True, state, "r")
    eligible = [(i, r) for i, r in enumerate(rules) if count >= r.threshold]
    decision = PolicyEngine(rules).evaluate(observation)
    if not eligible:
        assert decision.intervention.kind is InterventionType.NOOP
        return
    _, expected = max(
        eligible,
        key=lambda item: (
            item[1].priority,
            item[1].threshold,
            item[1].intervention.is_terminal,
            -item[0],
        ),
    )
    assert decision.intervention.policy == expected.policy_id
    assert decision.intervention.kind is expected.intervention


@given(st.lists(st.integers(0, 120), min_size=1, max_size=40), st.integers(1, 30))
def test_cooldown_law(offsets: list[int], cooldown: int) -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "cool",
                "repeated_tool_call",
                1,
                InterventionType.NUDGE,
                cooldown=timedelta(seconds=cooldown),
            )
        ]
    )
    until = None
    for offset in offsets:
        decision = engine.process(BehaviorEvent.tool_call("t", scope="s", timestamp=at(offset)))
        expected = until is None or until <= at(offset)
        assert decision.actionable == expected
        assert decision.suppressed == (not expected)
        if expected:
            until = at(offset) + timedelta(seconds=cooldown)


@given(st.lists(names, max_size=40), st.integers(1, 4))
def test_once_only_fires_at_most_once_per_history(sequence: list[str], threshold: int) -> None:
    streak = BehaviorEngine(
        policies=[
            PolicyRule(
                "once", "repeated_node_execution", threshold, InterventionType.NUDGE, once_only=True
            )
        ]
    )
    frequency = BehaviorEngine(
        policies=[
            PolicyRule("once", "event_frequency", threshold, InterventionType.NUDGE, once_only=True)
        ]
    )
    events = [BehaviorEvent(EventType.NODE_EXECUTION, scope="s", node_name=n) for n in sequence]
    streak_fired = sum(streak.process(event).actionable for event in events)
    frequency_fired = sum(frequency.process(event).actionable for event in events)
    runs, run, previous = [], 0, None
    for name in sequence:
        run, previous = (run + 1 if name == previous else 1), name
        runs.append(run)
    assert streak_fired == (1 if any(r >= threshold for r in runs) else 0)
    reached = [name for name, count in Counter(sequence).items() if count >= threshold]
    assert frequency_fired == len(reached), "frequency histories are tracked per identity"


aware_times = st.datetimes(timezones=st.just(UTC))
metadata_values = st.recursive(
    json_scalars,
    lambda inner: (
        st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=4), inner, max_size=3)
    ),
    max_leaves=8,
)
states = st.builds(
    BehaviorState,
    pattern_id=st.text(min_size=1, max_size=8),
    scope=st.text(min_size=1, max_size=8),
    count=st.integers(0, 10**6),
    first_seen=st.none() | aware_times,
    last_seen=st.none() | aware_times,
    previous_fingerprint=st.none() | st.text(max_size=8),
    current_fingerprint=st.none() | st.text(max_size=8),
    event_count=st.integers(0, 10**6),
    intervention_history=st.lists(st.text(max_size=5), max_size=4).map(tuple),
    cooldowns=st.dictionaries(st.text(max_size=5), aware_times, max_size=3),
    seen_event_ids=st.lists(st.text(max_size=8), max_size=5).map(tuple),
    emissions=st.lists(
        st.tuples(
            st.text(max_size=8),
            st.text(max_size=5),
            st.integers(0, 10**6),
            st.text(max_size=10),
        ),
        max_size=3,
    ).map(tuple),
    metadata=st.dictionaries(st.text(max_size=5), metadata_values, max_size=3),
    version=st.integers(0, 10**6),
)


@given(states)
def test_state_serialization_round_trips(state: BehaviorState) -> None:
    assert BehaviorState.from_json(state.to_json()) == state
    assert BehaviorState.from_dict(json.loads(state.to_json())) == state


xai_fields = st.sampled_from(
    [
        "event_type",
        "id",
        "timestamp",
        "sequence",
        "context",
        "node",
        "tool",
        "error",
        "status",
        "exception_type",
        "outcome",
        "thread_id",
        "run_id",
        "node_id",
        "node_name",
        "tool_name",
        "agent_name",
        "target_agent",
    ]
)
xai_scalars = (
    json_scalars
    | st.uuids()
    | st.datetimes(timezones=st.none() | st.just(UTC))
    | st.sampled_from(
        [
            "node.execution",
            "tool.execution",
            "execution.completed",
            "execution.failed",
            "delegation",
            "outcome",
            "completed",
            "succeeded",
            "failed",
            "timed_out",
            "cancelled",
            "interrupted",
            "CancelledError",
            "success",
            "2026-01-01T00:00:00+00:00",
        ]
    )
)
xai_payloads = st.dictionaries(
    xai_fields,
    st.recursive(
        xai_scalars,
        lambda inner: st.lists(inner, max_size=3) | st.dictionaries(xai_fields, inner, max_size=4),
        max_leaves=12,
    ),
    max_size=8,
)


@given(xai_payloads)
def test_the_xai_adapter_maps_any_mapping_to_a_valid_event(payload: dict[str, object]) -> None:
    event = LangGraphXAIEventAdapter().event(payload, scope="s")

    assert event.timestamp.utcoffset() is not None
    assert set(event.metadata) <= {"source", "xai_event_type", "sequence"}
    record_id = payload.get("id")
    if isinstance(record_id, UUID) or (isinstance(record_id, str) and record_id):
        assert event.event_id == event.provenance_ref == str(record_id)
    else:
        assert event.provenance_ref is None
    assert json.loads(event.to_json())["event_id"] == event.event_id
