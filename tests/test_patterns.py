from collections.abc import Callable

import pytest

from behaviorweave import (
    BehaviorEvent,
    ConsecutivePattern,
    EventType,
    FrequencyPattern,
    InMemoryBehaviorStateStore,
    OscillationPattern,
    Outcome,
    Pattern,
    PolicyConfigurationError,
    StreakPattern,
    built_in_patterns,
)
from support import at

REPEAT = ConsecutivePattern("repeat", frozenset({EventType.TOOL_CALL}))
FAILURES = StreakPattern(
    "failures", counts=frozenset({Outcome.FAILURE}), resets=frozenset({Outcome.SUCCESS})
)
PING_PONG = OscillationPattern("ping_pong", frozenset({EventType.AGENT_HANDOFF}))
FREQUENCY = FrequencyPattern("freq", frozenset({EventType.TOOL_CALL, EventType.NODE_EXECUTION}))


def _tool(name: str, seconds: float = 0, event_id: str | None = None) -> BehaviorEvent:
    return BehaviorEvent.tool_call(name, scope="s", timestamp=at(seconds), event_id=event_id)


def _outcome(outcome: Outcome, seconds: float = 0) -> BehaviorEvent:
    return BehaviorEvent.outcome_event(outcome, scope="s", timestamp=at(seconds))


def _handoff(source: str, target: str, seconds: float = 0) -> BehaviorEvent:
    return BehaviorEvent(
        EventType.AGENT_HANDOFF,
        scope="s",
        agent_name=source,
        target_agent=target,
        timestamp=at(seconds),
    )


def test_built_in_patterns() -> None:
    patterns = built_in_patterns()
    assert [p.pattern_id for p in patterns] == [
        "repeated_tool_call",
        "repeated_node_execution",
        "failure_streak",
        "retry_streak",
        "success_streak",
        "delegation_streak",
        "oscillation",
        "event_frequency",
    ]
    assert built_in_patterns() is patterns
    assert all(isinstance(p, Pattern) for p in patterns)


async def test_consecutive_pattern_counts_and_restarts() -> None:
    store = InMemoryBehaviorStateStore()
    names = ["a", "a", "a", "b", "a"]
    observations = [await REPEAT.observe(_tool(n, i), store) for i, n in enumerate(names)]
    assert [o.count for o in observations] == [1, 2, 3, 1, 1]
    assert all(o.accepted for o in observations)
    assert observations[2].reason == "'a' occurred 3 consecutive times"
    assert observations[0].reason == "'a' occurred 1 consecutive time"
    assert observations[2].state.first_seen == at(0)
    assert observations[3].state.first_seen == at(3)
    assert observations[3].state.previous_fingerprint == observations[2].fingerprint
    assert observations[4].state.event_count == 5
    assert observations[4].state.version == 5


async def test_redelivered_event_is_not_accepted() -> None:
    store = InMemoryBehaviorStateStore()
    event = _tool("a", event_id="same")
    first = await REPEAT.observe(event, store)
    second = await REPEAT.observe(event, store)
    assert (first.accepted, second.accepted) == (True, False)
    assert second.count == 1
    assert second.state == first.state


async def test_seen_event_window_is_bounded() -> None:
    store = InMemoryBehaviorStateStore()
    await REPEAT.observe(_tool("a", event_id="first"), store)
    for index in range(255):
        await REPEAT.observe(_tool("a", event_id=f"e{index}"), store)
    assert not (await REPEAT.observe(_tool("a", event_id="first"), store)).accepted
    await REPEAT.observe(_tool("a", event_id="one-more"), store)
    replay = await REPEAT.observe(_tool("a", event_id="first"), store)
    assert replay.accepted, "ids older than the retention window are accepted again"
    assert len(replay.state.seen_event_ids) == 256


async def test_streak_pattern_counts_resets_and_ignores() -> None:
    store = InMemoryBehaviorStateStore()
    sequence = [Outcome.FAILURE, Outcome.FAILURE, Outcome.SUCCESS, Outcome.FAILURE]
    observations = [await FAILURES.observe(_outcome(o, i), store) for i, o in enumerate(sequence)]
    assert [o.count for o in observations] == [1, 2, 0, 1]
    assert observations[1].reason == "2 consecutive failure outcomes"
    assert observations[0].reason == "1 consecutive failure outcome"
    assert observations[2].reason == "failure streak reset"
    assert observations[2].state.first_seen is None
    assert observations[3].state.first_seen == at(3)
    neutral = await FAILURES.observe(_outcome(Outcome.RETRY, 4), store)
    assert neutral.count == 1
    assert neutral.state.first_seen == at(3)
    assert (await FAILURES.observe(BehaviorEvent(EventType.CUSTOM, scope="s"), store)).count == 1


def test_streak_matching_uses_effective_outcome() -> None:
    retries = StreakPattern("retries", counts=frozenset({Outcome.RETRY}))
    assert retries.matches(BehaviorEvent(EventType.RETRY, scope="s"))
    assert retries.matches(_outcome(Outcome.RETRY))
    assert not retries.matches(_outcome(Outcome.SUCCESS))
    assert not retries.matches(BehaviorEvent(EventType.CUSTOM, scope="s"))
    assert FAILURES.matches(_outcome(Outcome.SUCCESS))
    # pyrefly: ignore[bad-argument-type]
    failed_node = BehaviorEvent(EventType.NODE_EXECUTION, scope="s", outcome="failure")
    assert FAILURES.matches(failed_node)


async def test_oscillation_counts_back_and_forth_transitions() -> None:
    store = InMemoryBehaviorStateStore()
    hops = [("a", "b"), ("b", "a"), ("a", "b"), ("b", "a"), ("b", "a"), ("a", "c")]
    observations = [
        await PING_PONG.observe(_handoff(s, t, i), store) for i, (s, t) in enumerate(hops)
    ]
    assert [o.count for o in observations] == [0, 0, 1, 2, 0, 0]
    assert observations[0].reason == "no oscillation"
    assert observations[2].reason == "1 consecutive back-and-forth transition (latest: 'a->b')"
    assert observations[3].reason == "2 consecutive back-and-forth transitions (latest: 'b->a')"
    assert observations[3].state.first_seen == at(2)
    assert observations[4].state.first_seen is None


async def test_frequency_pattern_tracks_each_identity() -> None:
    store = InMemoryBehaviorStateStore()
    counts = [(await FREQUENCY.observe(_tool(n, i), store)).count for i, n in enumerate("abab")]
    assert counts == [1, 1, 2, 2]
    node = BehaviorEvent(EventType.NODE_EXECUTION, scope="s", node_name="a")
    observation = await FREQUENCY.observe(node, store)
    assert observation.count == 1, "identities are tracked per event type"
    assert observation.reason == "'a' occurred 1 time"
    assert (await FREQUENCY.observe(_tool("a", 9), store)).reason == "'a' occurred 3 times"
    assert not FREQUENCY.matches(_outcome(Outcome.SUCCESS))


async def test_state_keys_cannot_collide_across_scopes() -> None:
    store = InMemoryBehaviorStateStore()
    first = ConsecutivePattern("b:c", frozenset({EventType.TOOL_CALL}))
    second = ConsecutivePattern("c", frozenset({EventType.TOOL_CALL}))
    one = await first.observe(BehaviorEvent.tool_call("t", scope="a"), store)
    two = await second.observe(BehaviorEvent.tool_call("t", scope="a:b"), store)
    assert one.state_key != two.state_key
    assert (one.count, two.count) == (1, 1)


def test_patterns_coerce_event_types() -> None:
    # pyrefly: ignore[bad-argument-type]
    pattern = ConsecutivePattern("p", ["tool_call"])
    assert pattern.event_types == frozenset({EventType.TOOL_CALL})
    # pyrefly: ignore[bad-argument-type]
    streak = StreakPattern("s", counts=["failure"])
    assert streak.counts == frozenset({Outcome.FAILURE})


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ConsecutivePattern("", frozenset({EventType.TOOL_CALL})),
        lambda: ConsecutivePattern("p", frozenset()),
        # pyrefly: ignore[bad-argument-type]
        lambda: OscillationPattern("p", frozenset({"bogus"})),
        lambda: FrequencyPattern(" ", frozenset({EventType.TOOL_CALL})),
        lambda: StreakPattern("s", counts=frozenset()),
        # pyrefly: ignore[bad-argument-type]
        lambda: StreakPattern("s", counts=frozenset({"nope"})),
        lambda: StreakPattern(
            "s", counts=frozenset({Outcome.FAILURE}), resets=frozenset({Outcome.FAILURE})
        ),
    ],
)
def test_pattern_configuration_is_validated(factory: Callable[[], object]) -> None:
    with pytest.raises(PolicyConfigurationError):
        factory()
