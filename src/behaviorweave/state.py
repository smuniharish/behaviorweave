from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BehaviorState:
    pattern_id: str
    scope: str
    count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    previous_fingerprint: str | None = None
    current_fingerprint: str | None = None
    event_count: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None
    threshold_state: bool = False
    cooldown_until: datetime | None = None
    intervention_history: tuple[str, ...] = ()
    seen_event_ids: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
    version: int = 0

    def json(self) -> str:
        data = (
            {**self.__dict__}
            if hasattr(self, "__dict__")
            else {name: getattr(self, name) for name in self.__dataclass_fields__}
        )
        for key in ("first_seen", "last_seen", "window_start", "window_end", "cooldown_until"):
            if data[key]:
                data[key] = data[key].isoformat()
        return json.dumps(data, sort_keys=True)


class BehaviorStateStore(Protocol):
    def get(self, key: str) -> BehaviorState | None: ...
    def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState: ...
    def put(self, key: str, state: BehaviorState) -> None: ...
    def delete(self, key: str) -> None: ...


class InMemoryBehaviorStateStore:
    def __init__(self, ttl: timedelta | None = None) -> None:
        self._states: dict[str, tuple[BehaviorState, datetime | None]] = {}
        self._lock = RLock()
        self._ttl = ttl

    def get(self, key: str) -> BehaviorState | None:
        with self._lock:
            entry = self._states.get(key)
            if entry is None:
                return None
            state, expires = entry
            if expires and expires <= datetime.now(UTC):
                del self._states[key]
                return None
            return copy.deepcopy(state)

    def put(self, key: str, state: BehaviorState) -> None:
        with self._lock:
            expires = datetime.now(UTC) + self._ttl if self._ttl else None
            self._states[key] = (copy.deepcopy(state), expires)

    def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState:
        with self._lock:
            current = self.get(key)
            updated = fn(current)
            if updated.count < 0:
                raise ValueError("behavior state count cannot be negative")
            self.put(key, updated)
            return copy.deepcopy(updated)

    def delete(self, key: str) -> None:
        with self._lock:
            self._states.pop(key, None)


def advance_state(
    current: BehaviorState | None,
    *,
    pattern_id: str,
    scope: str,
    fingerprint: str,
    event_id: str,
    timestamp: datetime,
    consecutive: bool = True,
) -> BehaviorState:
    if current and event_id in current.seen_event_ids:
        return current
    same = current is not None and current.current_fingerprint == fingerprint
    count = (current.count + 1) if current and (same or not consecutive) else 1
    seen = ((current.seen_event_ids if current else ()) + (event_id,))[-256:]
    return BehaviorState(
        pattern_id=pattern_id,
        scope=scope,
        count=count,
        first_seen=current.first_seen if current and count > 1 else timestamp,
        last_seen=timestamp,
        previous_fingerprint=current.current_fingerprint if current else None,
        current_fingerprint=fingerprint,
        event_count=(current.event_count if current else 0) + 1,
        window_start=current.window_start if current and count > 1 else timestamp,
        window_end=timestamp,
        threshold_state=current.threshold_state if current else False,
        cooldown_until=current.cooldown_until if current else None,
        intervention_history=current.intervention_history if current else (),
        seen_event_ids=seen,
        metadata=current.metadata if current else {},
        version=(current.version if current else 0) + 1,
    )


def with_cooldown(state: BehaviorState, until: datetime, intervention: str) -> BehaviorState:
    return replace(
        state,
        cooldown_until=until,
        intervention_history=(*state.intervention_history, intervention),
    )
