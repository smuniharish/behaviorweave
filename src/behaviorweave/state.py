"""Behavior state snapshots and the state-store boundary."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, Protocol

from ._util import EMPTY_MAP, canonical, freeze
from .errors import StateStoreError

__all__ = ["BehaviorState", "BehaviorStateStore", "InMemoryBehaviorStateStore"]

# How many recent event IDs (and emitted decisions) a pattern history remembers for idempotency.
_EVENT_RETENTION = 256


def _empty_map() -> Mapping[str, Any]:
    return EMPTY_MAP


@dataclass(frozen=True, slots=True)
class BehaviorState:
    """Immutable snapshot of one pattern's history within one scope.

    Patterns create and advance states; policies read them. Construct one directly only when
    implementing a custom pattern or a custom
    [`BehaviorStateStore`][behaviorweave.BehaviorStateStore].

    Attributes:
        pattern_id: Pattern that owns this history.
        scope: Behavior isolation boundary.
        count: Current pattern count (for example, the length of the active streak).
        first_seen: Time at which the active count began, or ``None`` when the count is zero.
        last_seen: Time of the most recently accepted event.
        previous_fingerprint: Identity observed immediately before ``current_fingerprint``.
        current_fingerprint: Identity of the most recently accepted event.
        event_count: Number of accepted events represented by this state.
        intervention_history: Policy IDs that have produced an intervention, in order of first
            emission, without duplicates.
        cooldowns: Policy ID to the time until which that policy is cooling down.
        seen_event_ids: Most recent accepted event IDs, used to recognize redelivered events.
        emissions: Interventions recently emitted from this history, oldest first, as
            ``(event ID, policy ID, count, reason)`` tuples, so that a redelivered event
            receives its original decision.
        metadata: Read-only, JSON-compatible state metadata for custom patterns.
        version: Monotonically increasing version, advanced on every write.

    Raises:
        StateStoreError: If ``count``, ``event_count``, or ``version`` is negative.
    """

    pattern_id: str
    scope: str
    count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    previous_fingerprint: str | None = None
    current_fingerprint: str | None = None
    event_count: int = 0
    intervention_history: tuple[str, ...] = ()
    cooldowns: Mapping[str, datetime] = field(default_factory=_empty_map)
    seen_event_ids: tuple[str, ...] = ()
    emissions: tuple[tuple[str, str, int, str], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=_empty_map)
    version: int = 0

    def __post_init__(self) -> None:
        if min(self.count, self.event_count, self.version) < 0:
            raise StateStoreError("count, event_count, and version must be non-negative")
        object.__setattr__(self, "cooldowns", freeze(self.cooldowns))
        object.__setattr__(self, "metadata", freeze(self.metadata))
        if not isinstance(self.intervention_history, tuple):
            object.__setattr__(self, "intervention_history", tuple(self.intervention_history))
        if not isinstance(self.seen_event_ids, tuple):
            object.__setattr__(self, "seen_event_ids", tuple(self.seen_event_ids))
        if not isinstance(self.emissions, tuple):
            object.__setattr__(self, "emissions", tuple(map(tuple, self.emissions)))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dictionary that `from_dict` can restore."""
        return {
            "pattern_id": self.pattern_id,
            "scope": self.scope,
            "count": self.count,
            "first_seen": _iso(self.first_seen),
            "last_seen": _iso(self.last_seen),
            "previous_fingerprint": self.previous_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "event_count": self.event_count,
            "intervention_history": list(self.intervention_history),
            "cooldowns": {policy: until.isoformat() for policy, until in self.cooldowns.items()},
            "seen_event_ids": list(self.seen_event_ids),
            "emissions": [list(entry) for entry in self.emissions],
            "metadata": canonical(self.metadata),
            "version": self.version,
        }

    def to_json(self) -> str:
        """Return a stable, key-sorted JSON representation of the state."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BehaviorState:
        """Restore a state produced by `to_dict`.

        Unknown keys are ignored so that newer serialized states remain readable.

        Raises:
            StateStoreError: If required keys are missing or values are malformed.
        """
        try:
            return cls(
                pattern_id=str(data["pattern_id"]),
                scope=str(data["scope"]),
                count=int(data.get("count", 0)),
                first_seen=_parse_time(data.get("first_seen")),
                last_seen=_parse_time(data.get("last_seen")),
                previous_fingerprint=_optional_text(data.get("previous_fingerprint")),
                current_fingerprint=_optional_text(data.get("current_fingerprint")),
                event_count=int(data.get("event_count", 0)),
                intervention_history=tuple(
                    str(item) for item in data.get("intervention_history", ())
                ),
                cooldowns={
                    str(policy): _require_time(until)
                    for policy, until in dict(data.get("cooldowns") or {}).items()
                },
                seen_event_ids=tuple(str(item) for item in data.get("seen_event_ids", ())),
                emissions=tuple(_emission(entry) for entry in data.get("emissions") or ()),
                metadata=dict(data.get("metadata") or {}),
                version=int(data.get("version", 0)),
            )
        except StateStoreError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise StateStoreError(f"invalid behavior state: {exc!r}") from exc

    @classmethod
    def from_json(cls, raw: str | bytes) -> BehaviorState:
        """Restore a state produced by `to_json`.

        Raises:
            StateStoreError: If ``raw`` is not a JSON object describing a valid state.
        """
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise StateStoreError(f"invalid behavior state JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise StateStoreError("behavior state JSON must be an object")
        return cls.from_dict(data)


class BehaviorStateStore(Protocol):
    """Storage boundary for behavior state.

    The engine only requires `update`; the other methods support application
    inspection and lifecycle management. Implement this protocol to keep state in a durable
    or distributed backend.
    """

    def get(self, key: str) -> BehaviorState | None:
        """Return the state stored under ``key``, or ``None`` when absent or expired."""
        ...

    def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState:
        """Atomically replace the state under ``key`` with ``fn(current)`` and return it.

        Implementations must serialize concurrent updates of the same key. Optimistic
        implementations may invoke ``fn`` more than once, but must commit only the result
        of the final invocation.
        """
        ...

    def put(self, key: str, state: BehaviorState) -> None:
        """Store ``state`` under ``key``, replacing any existing state."""
        ...

    def delete(self, key: str) -> None:
        """Remove the state stored under ``key``, if any."""
        ...


class InMemoryBehaviorStateStore:
    """Thread-safe, process-local state store with optional expiry.

    Suitable for development, tests, and single-process services. State is not shared between
    processes and is lost on restart; implement
    [`BehaviorStateStore`][behaviorweave.BehaviorStateStore] for durable or distributed
    deployments.

    Args:
        ttl: Optional positive lifetime for each entry, refreshed on every write. Expired
            entries are never returned and are purged periodically.
        clock: Optional zero-argument callable returning the current timezone-aware time.
            Defaults to UTC wall-clock time; override it in tests.

    Raises:
        StateStoreError: If ``ttl`` is not positive.
    """

    _PURGE_EVERY = 256

    def __init__(
        self,
        ttl: timedelta | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl is not None and ttl <= timedelta(0):
            raise StateStoreError("ttl must be a positive timedelta")
        self._ttl = ttl
        self._clock = clock if clock is not None else _utc_now
        self._states: dict[str, tuple[BehaviorState, datetime | None]] = {}
        self._lock = RLock()
        self._writes = 0

    def get(self, key: str) -> BehaviorState | None:
        """Return the state stored under ``key``, or ``None`` when absent or expired."""
        with self._lock:
            state = self._load(key)
            return _detach(state) if state is not None else None

    def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState:
        """Atomically replace the state under ``key`` with ``fn(current)`` and return it.

        Raises:
            StateStoreError: If ``fn`` does not return a ``BehaviorState``.
        """
        with self._lock:
            current = self._load(key)
            updated = fn(_detach(current) if current is not None else None)
            if not isinstance(updated, BehaviorState):
                raise StateStoreError("update function must return a BehaviorState")
            stored = _detach(updated)
            self._store(key, stored)
            return _detach(stored)

    def put(self, key: str, state: BehaviorState) -> None:
        """Store ``state`` under ``key``, replacing any existing state.

        Raises:
            StateStoreError: If ``state`` is not a ``BehaviorState``.
        """
        if not isinstance(state, BehaviorState):
            raise StateStoreError("state must be a BehaviorState")
        with self._lock:
            self._store(key, _detach(state))

    def delete(self, key: str) -> None:
        """Remove the state stored under ``key``, if any."""
        with self._lock:
            self._states.pop(key, None)

    def clear(self, scope: str | None = None) -> int:
        """Remove every state, or only the states of one ``scope``.

        Call this when a conversation or run ends to release its behavioral history. Expired
        states are dropped too, but only live states are counted.

        Returns:
            The number of removed live states.
        """
        with self._lock:
            now = self._clock()
            if scope is None:
                removed = list(self._states.values())
                self._states.clear()
            else:
                keys = [key for key, (state, _) in self._states.items() if state.scope == scope]
                removed = [self._states.pop(key) for key in keys]
            return sum(1 for _, expires in removed if expires is None or expires > now)

    def purge_expired(self) -> int:
        """Remove every expired state immediately.

        Returns:
            The number of removed states.
        """
        with self._lock:
            return self._purge(self._clock())

    def _load(self, key: str) -> BehaviorState | None:
        entry = self._states.get(key)
        if entry is None:
            return None
        state, expires = entry
        if expires is not None and expires <= self._clock():
            del self._states[key]
            return None
        return state

    def _store(self, key: str, state: BehaviorState) -> None:
        expires = None
        if self._ttl is not None:
            now = self._clock()
            expires = now + self._ttl
            self._writes += 1
            if self._writes % self._PURGE_EVERY == 0:
                self._purge(now)
        self._states[key] = (state, expires)

    def _purge(self, now: datetime) -> int:
        expired = [
            key
            for key, (_, expires) in self._states.items()
            if expires is not None and expires <= now
        ]
        for key in expired:
            del self._states[key]
        return len(expired)


def _detach(state: BehaviorState) -> BehaviorState:
    """Isolate the only field that may hold caller-mutable nested values."""
    if not state.metadata:
        return state
    return replace(state, metadata=copy.deepcopy(dict(state.metadata)))


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _parse_time(value: object) -> datetime | None:
    return None if value is None else _require_time(value)


def _emission(value: object) -> tuple[str, str, int, str]:
    if not isinstance(value, list | tuple) or len(value) != 4:
        raise ValueError(f"emission must be [event_id, policy, count, reason], got {value!r}")
    event_id, policy, count, reason = value
    return str(event_id), str(policy), int(count), str(reason)


def _require_time(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.utcoffset() is None:
        raise StateStoreError(f"timestamp must be timezone-aware: {value!r}")
    return parsed
