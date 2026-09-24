from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .events import BehaviorEvent, EventType, Outcome
from .state import BehaviorState, BehaviorStateStore, advance_state


@dataclass(frozen=True, slots=True)
class PatternObservation:
    pattern_id: str
    scope: str
    fingerprint: str
    state_key: str
    count: int
    crossed: bool
    state: BehaviorState
    reason: str


class Pattern(Protocol):
    @property
    def pattern_id(self) -> str: ...

    def matches(self, event: BehaviorEvent) -> bool: ...
    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation: ...


@dataclass(frozen=True, slots=True)
class ConsecutivePattern:
    pattern_id: str
    event_types: frozenset[EventType]
    outcome: Outcome | None = None
    identity_field: str = "identity"

    def matches(self, event: BehaviorEvent) -> bool:
        return event.event_type in self.event_types and (
            self.outcome is None or event.outcome is self.outcome
        )

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        fingerprint = event.identity()
        key = f"{event.scope}:{self.pattern_id}"
        previous = store.get(key)
        state = store.update(
            key,
            lambda current: advance_state(
                current,
                pattern_id=self.pattern_id,
                scope=event.scope,
                fingerprint=fingerprint,
                event_id=event.idempotency_key(),
                timestamp=event.timestamp,
            ),
        )
        return PatternObservation(
            self.pattern_id,
            event.scope,
            fingerprint,
            key,
            state.count,
            state.count > (previous.count if previous else 0),
            state,
            f"{self.pattern_id} observed {state.count} consecutive times",
        )


@dataclass(frozen=True, slots=True)
class FrequencyPattern:
    pattern_id: str
    event_types: frozenset[EventType]
    window_size: int = 10

    def matches(self, event: BehaviorEvent) -> bool:
        return event.event_type in self.event_types

    def observe(self, event: BehaviorEvent, store: BehaviorStateStore) -> PatternObservation:
        fingerprint = event.identity()
        key = f"{event.scope}:{self.pattern_id}:{fingerprint}"
        state = store.update(
            key,
            lambda current: advance_state(
                current,
                pattern_id=self.pattern_id,
                scope=event.scope,
                fingerprint=fingerprint,
                event_id=event.idempotency_key(),
                timestamp=event.timestamp,
                consecutive=False,
            ),
        )
        return PatternObservation(
            self.pattern_id,
            event.scope,
            fingerprint,
            key,
            state.count,
            True,
            state,
            f"{fingerprint} occurred {state.count} times",
        )


def built_in_patterns() -> tuple[Pattern, ...]:
    return (
        ConsecutivePattern("repeated_tool_call", frozenset({EventType.TOOL_CALL})),
        ConsecutivePattern("repeated_node_execution", frozenset({EventType.NODE_EXECUTION})),
        ConsecutivePattern("failure_streak", frozenset({EventType.OUTCOME}), Outcome.FAILURE),
        ConsecutivePattern(
            "retry_streak", frozenset({EventType.RETRY, EventType.OUTCOME}), Outcome.RETRY
        ),
        ConsecutivePattern("success_streak", frozenset({EventType.OUTCOME}), Outcome.SUCCESS),
        ConsecutivePattern("delegation_streak", frozenset({EventType.DELEGATION})),
        FrequencyPattern("event_frequency", frozenset(set(EventType))),
    )
