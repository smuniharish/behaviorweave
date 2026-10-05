"""Deterministic behavioral pattern detectors.

A pattern answers *what is happening*: it matches events, advances its scoped state
atomically, and reports a [`PatternObservation`][behaviorweave.PatternObservation]. It never
decides what to do about it; that is the job of policies.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .errors import PolicyConfigurationError
from .events import BehaviorEvent, EventType, Outcome
from .state import _EVENT_RETENTION, BehaviorState, BehaviorStateStore

__all__ = [
    "ConsecutivePattern",
    "FrequencyPattern",
    "OscillationPattern",
    "Pattern",
    "PatternObservation",
    "StreakPattern",
    "built_in_patterns",
]

# (next count, whether the event continues the active run)
type _Step = tuple[int, bool]


@dataclass(frozen=True, slots=True)
class PatternObservation:
    """Result of one pattern observing one event.

    Attributes:
        pattern_id: Pattern that made the observation.
        scope: Scope in which the event was observed.
        fingerprint: Identity the pattern compared.
        state_key: Opaque reference to the associated state. Pass it through unchanged; never
            parse or construct it.
        count: Pattern count after the event was applied.
        accepted: ``False`` when the event was a redelivery and left the state unchanged.
        state: Immutable state snapshot after the event was applied.
        reason: Deterministic, human-readable summary of the observation.
    """

    pattern_id: str
    scope: str
    fingerprint: str
    state_key: str
    count: int
    accepted: bool
    state: BehaviorState
    reason: str


@runtime_checkable
class Pattern(Protocol):
    """Protocol implemented by every pattern detector.

    Implementations must be deterministic, must advance state only through
    [`BehaviorStateStore.update`][behaviorweave.BehaviorStateStore.update], and must report a
    redelivered event (same ``event_id``) as not ``accepted`` without changing its count.
    """

    @property
    def pattern_id(self) -> str:
        """Unique identifier that policies use to reference this pattern."""
        ...

    def matches(self, event: BehaviorEvent) -> bool:
        """Return whether this pattern observes ``event``."""
        ...

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        """Apply ``event`` to the pattern's state in ``store`` and report the observation."""
        ...


@dataclass(frozen=True, slots=True)
class ConsecutivePattern:
    """Counts consecutive events that share one identity.

    The count grows while the same [identity][behaviorweave.BehaviorEvent.identity] repeats and
    restarts at 1 when a different identity arrives. Built-ins use it for repeated tool calls
    (same tool and arguments), repeated node executions, and repeated delegations.

    Attributes:
        pattern_id: Unique pattern identifier.
        event_types: Event types this pattern observes.
    """

    pattern_id: str
    event_types: frozenset[EventType]

    def __post_init__(self) -> None:
        _validate_pattern_id(self.pattern_id)
        object.__setattr__(self, "event_types", _event_types(self.event_types))

    def matches(self, event: BehaviorEvent) -> bool:
        """Return whether ``event`` has one of the configured event types."""
        return event.event_type in self.event_types

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        """Advance the consecutive-identity count for ``event``'s scope."""
        fingerprint = event.identity()
        label = _label(event)

        def step(current: BehaviorState | None) -> _Step:
            if current is not None and current.count and current.current_fingerprint == fingerprint:
                return current.count + 1, True
            return 1, False

        return _observe(
            self.pattern_id,
            event,
            store,
            _state_key(event.scope, self.pattern_id),
            fingerprint,
            step,
            lambda count: f"'{label}' occurred {count} consecutive {_times(count)}",
        )


@dataclass(frozen=True, slots=True)
class StreakPattern:
    """Counts consecutive outcomes, restarting when a resetting outcome arrives.

    An event's outcome is its ``outcome`` field; a `retry` event without an outcome counts as
    [`Outcome.RETRY`][behaviorweave.Outcome.RETRY]. Outcomes in ``counts`` extend the streak,
    outcomes in ``resets`` restart it at zero, and other outcomes are ignored. Streaks are
    scope-wide: outcomes from different tools or nodes in one scope share a streak.

    Attributes:
        pattern_id: Unique pattern identifier.
        counts: Outcomes that extend the streak.
        resets: Outcomes that restart the streak at zero.
    """

    pattern_id: str
    counts: frozenset[Outcome]
    resets: frozenset[Outcome] = frozenset()

    def __post_init__(self) -> None:
        _validate_pattern_id(self.pattern_id)
        counts = _outcomes(self.counts)
        resets = _outcomes(self.resets)
        if not counts:
            raise PolicyConfigurationError("counts must contain at least one outcome")
        if counts & resets:
            raise PolicyConfigurationError("an outcome cannot both count toward and reset a streak")
        object.__setattr__(self, "counts", counts)
        object.__setattr__(self, "resets", resets)

    def matches(self, event: BehaviorEvent) -> bool:
        """Return whether ``event`` carries an outcome that counts toward or resets the streak."""
        outcome = _effective_outcome(event)
        return outcome is not None and (outcome in self.counts or outcome in self.resets)

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        """Extend, reset, or keep the streak for ``event``'s scope."""
        outcome = _effective_outcome(event)
        hit = outcome in self.counts
        reset = outcome in self.resets
        label = "/".join(sorted(item.value for item in self.counts))

        def step(current: BehaviorState | None) -> _Step:
            count = current.count if current is not None else 0
            if hit:
                return count + 1, count > 0
            if reset:
                return 0, False
            return count, True

        def describe(count: int) -> str:
            if count == 0:
                return f"{label} streak reset"
            return f"{count} consecutive {label} {'outcome' if count == 1 else 'outcomes'}"

        return _observe(
            self.pattern_id,
            event,
            store,
            _state_key(event.scope, self.pattern_id),
            outcome.value if outcome is not None else event.event_type.value,
            step,
            describe,
        )


@dataclass(frozen=True, slots=True)
class OscillationPattern:
    """Counts consecutive back-and-forth transitions between two identities.

    The count grows each time an event repeats the identity seen two events earlier while
    differing from the previous one: ``A, B, A`` is one transition back and ``A, B, A, B`` is
    two. Any other event restarts the count at zero. The built-in instance detects agents
    handing work back and forth.

    Attributes:
        pattern_id: Unique pattern identifier.
        event_types: Event types this pattern observes.
    """

    pattern_id: str
    event_types: frozenset[EventType]

    def __post_init__(self) -> None:
        _validate_pattern_id(self.pattern_id)
        object.__setattr__(self, "event_types", _event_types(self.event_types))

    def matches(self, event: BehaviorEvent) -> bool:
        """Return whether ``event`` has one of the configured event types."""
        return event.event_type in self.event_types

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        """Advance the oscillation count for ``event``'s scope."""
        fingerprint = event.identity()
        label = _label(event)

        def step(current: BehaviorState | None) -> _Step:
            if (
                current is not None
                and fingerprint == current.previous_fingerprint
                and fingerprint != current.current_fingerprint
            ):
                return current.count + 1, current.count > 0
            return 0, False

        def describe(count: int) -> str:
            if count == 0:
                return "no oscillation"
            return f"{count} consecutive back-and-forth {_transitions(count)} (latest: '{label}')"

        return _observe(
            self.pattern_id,
            event,
            store,
            _state_key(event.scope, self.pattern_id),
            fingerprint,
            step,
            describe,
        )


@dataclass(frozen=True, slots=True)
class FrequencyPattern:
    """Counts every occurrence of each event identity within a scope.

    Unlike streaks, the count never resets; it grows for as long as the scope's state is
    retained. Each identity is tracked separately per event type.

    Attributes:
        pattern_id: Unique pattern identifier.
        event_types: Event types this pattern observes.
    """

    pattern_id: str
    event_types: frozenset[EventType]

    def __post_init__(self) -> None:
        _validate_pattern_id(self.pattern_id)
        object.__setattr__(self, "event_types", _event_types(self.event_types))

    def matches(self, event: BehaviorEvent) -> bool:
        """Return whether ``event`` has one of the configured event types."""
        return event.event_type in self.event_types

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        """Increment the occurrence count of ``event``'s identity in its scope."""
        fingerprint = f"{event.event_type.value}/{event.identity()}"
        label = _label(event)

        def step(current: BehaviorState | None) -> _Step:
            return (current.count + 1, True) if current is not None else (1, False)

        return _observe(
            self.pattern_id,
            event,
            store,
            _state_key(event.scope, self.pattern_id, fingerprint),
            fingerprint,
            step,
            lambda count: f"'{label}' occurred {count} {_times(count)}",
        )


def _observe(
    pattern_id: str,
    event: BehaviorEvent,
    store: BehaviorStateStore,
    key: str,
    fingerprint: str,
    step: Callable[[BehaviorState | None], _Step],
    describe: Callable[[int], str],
) -> PatternObservation:
    accepted = False

    def apply(current: BehaviorState | None) -> BehaviorState:
        nonlocal accepted
        if current is not None and event.event_id in current.seen_event_ids:
            accepted = False
            return current
        accepted = True
        count, continues = step(current)
        return _advance(current, pattern_id, event, fingerprint, count, continues)

    state = store.update(key, apply)
    return PatternObservation(
        pattern_id=pattern_id,
        scope=event.scope,
        fingerprint=fingerprint,
        state_key=key,
        count=state.count,
        accepted=accepted,
        state=state,
        reason=describe(state.count),
    )


def _advance(
    current: BehaviorState | None,
    pattern_id: str,
    event: BehaviorEvent,
    fingerprint: str,
    count: int,
    continues: bool,
) -> BehaviorState:
    timestamp = event.timestamp
    if current is None:
        return BehaviorState(
            pattern_id=pattern_id,
            scope=event.scope,
            count=count,
            first_seen=timestamp if count else None,
            last_seen=timestamp,
            current_fingerprint=fingerprint,
            event_count=1,
            seen_event_ids=(event.event_id,),
            version=1,
        )
    if count == 0:
        first_seen = None
    elif continues:
        first_seen = current.first_seen
    else:
        first_seen = timestamp
    return BehaviorState(
        pattern_id=pattern_id,
        scope=current.scope,
        count=count,
        first_seen=first_seen,
        last_seen=timestamp,
        previous_fingerprint=current.current_fingerprint,
        current_fingerprint=fingerprint,
        event_count=current.event_count + 1,
        intervention_history=current.intervention_history,
        cooldowns=current.cooldowns,
        seen_event_ids=(*current.seen_event_ids[1 - _EVENT_RETENTION :], event.event_id),
        emissions=current.emissions,
        metadata=current.metadata,
        version=current.version + 1,
    )


def _state_key(*parts: str) -> str:
    # Length prefixes keep keys unambiguous whatever characters scopes or identities contain.
    return "/".join(f"{len(part)}:{part}" for part in parts)


def _validate_pattern_id(pattern_id: object) -> None:
    if not isinstance(pattern_id, str) or not pattern_id.strip():
        raise PolicyConfigurationError("pattern_id must be a non-empty string")


def _event_types(values: Iterable[EventType | str]) -> frozenset[EventType]:
    try:
        types = frozenset(EventType(value) for value in values)
    except ValueError as exc:
        raise PolicyConfigurationError(f"unknown event type: {exc}") from None
    if not types:
        raise PolicyConfigurationError("event_types must contain at least one event type")
    return types


def _outcomes(values: Iterable[Outcome | str]) -> frozenset[Outcome]:
    try:
        return frozenset(Outcome(value) for value in values)
    except ValueError as exc:
        raise PolicyConfigurationError(f"unknown outcome: {exc}") from None


def _effective_outcome(event: BehaviorEvent) -> Outcome | None:
    if event.outcome is not None:
        return event.outcome
    return Outcome.RETRY if event.event_type is EventType.RETRY else None


def _label(event: BehaviorEvent) -> str:
    if event.event_type is EventType.TOOL_CALL and event.tool_name:
        return event.tool_name
    return event.identity()


def _times(count: int) -> str:
    return "time" if count == 1 else "times"


def _transitions(count: int) -> str:
    return "transition" if count == 1 else "transitions"


_BUILT_IN_PATTERNS: tuple[Pattern, ...] = (
    ConsecutivePattern("repeated_tool_call", frozenset({EventType.TOOL_CALL})),
    ConsecutivePattern("repeated_node_execution", frozenset({EventType.NODE_EXECUTION})),
    StreakPattern(
        "failure_streak", counts=frozenset({Outcome.FAILURE}), resets=frozenset({Outcome.SUCCESS})
    ),
    StreakPattern(
        "retry_streak", counts=frozenset({Outcome.RETRY}), resets=frozenset({Outcome.SUCCESS})
    ),
    StreakPattern(
        "success_streak",
        counts=frozenset({Outcome.SUCCESS}),
        resets=frozenset({Outcome.FAILURE, Outcome.RETRY}),
    ),
    ConsecutivePattern("delegation_streak", frozenset({EventType.DELEGATION})),
    OscillationPattern("oscillation", frozenset({EventType.AGENT_HANDOFF, EventType.DELEGATION})),
    FrequencyPattern("event_frequency", frozenset(EventType)),
)


def built_in_patterns() -> tuple[Pattern, ...]:
    """Return the standard patterns used when an engine is created without ``patterns``.

    | Pattern ID | Detects |
    | --- | --- |
    | `repeated_tool_call` | Consecutive calls to the same tool with the same arguments. |
    | `repeated_node_execution` | Consecutive executions of the same graph node. |
    | `failure_streak` | Consecutive failures; reset by a success. |
    | `retry_streak` | Consecutive retries; reset by a success. |
    | `success_streak` | Consecutive successes; reset by a failure or retry. |
    | `delegation_streak` | Consecutive delegations to the same agent. |
    | `oscillation` | Handoffs or delegations bouncing back and forth between two agents. |
    | `event_frequency` | Total occurrences of each event identity. |
    """
    return _BUILT_IN_PATTERNS
