# State and concurrency

Patterns keep a small, immutable [`BehaviorState`][behaviorweave.BehaviorState] for each
pattern history: per scope for consecutive, streak, and oscillation patterns, and per scope
and identity for frequency patterns. A state records the current count, when the active run
began, the most recent identities, the policies that have fired, per-policy cooldowns, and,
for idempotency, the 256 most recent event IDs together with the decisions emitted for them.

## The default store

Unless you pass a `state_store`, the engine uses an
[`InMemoryBehaviorStateStore`][behaviorweave.InMemoryBehaviorStateStore]: thread-safe,
process-local, and lost on restart.

```python
from datetime import timedelta

from behaviorweave import BehaviorEngine, InMemoryBehaviorStateStore

store = InMemoryBehaviorStateStore(ttl=timedelta(hours=24))
engine = BehaviorEngine(state_store=store)
```

- **Expiry.** With a `ttl`, each history expires after that period without writes. Expired
  entries are never returned and are purged periodically; call `purge_expired()` to purge
  immediately.
- **Lifecycle.** Call `store.clear(scope)` when a conversation ends to release its history,
  or `store.clear()` to reset everything.

## Concurrency guarantees

Every state transition goes through the store's atomic `update`, so one engine can be
shared by many threads or asyncio tasks in one process:

- no event is lost when concurrent events update the same history;
- a redelivered event is counted once, even when the copies arrive concurrently; a
  redelivery that arrives after the original delivery was processed receives the original
  decision again if it was actionable, and a `noop` otherwise;
- a `once_only` policy fires exactly once, even when several events cross its threshold
  at the same moment: the engine records each emission with an atomic compare-and-set, and
  any losing event receives a suppressed `noop`.

These guarantees are verified by the test suite, including multi-threaded stress tests and
stateful, model-based property tests of the engine and the store.

!!! note "Distributed deployments"
    The in-memory store does not coordinate across processes. To share behavioral history
    between workers or survive restarts, implement
    [`BehaviorStateStore`][behaviorweave.BehaviorStateStore] on a backend with atomic
    updates. `BehaviorState.to_json()` and `BehaviorState.from_json()` provide a lossless
    serialized form for JSON-compatible metadata.

## Implementing a durable store

The engine only calls `update(key, fn)`. Your implementation must apply `fn` atomically per
key; an optimistic implementation may call `fn` more than once but must commit only the
result of the final call. Keys are opaque strings: store them as-is and never parse them.

```python
import threading

from behaviorweave import BehaviorState


class JsonDictStore:
    """Toy store: serialized states in a dict, standing in for Redis or SQL."""

    def __init__(self) -> None:
        self._rows: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> BehaviorState | None:
        raw = self._rows.get(key)
        return BehaviorState.from_json(raw) if raw is not None else None

    def update(self, key, fn):
        with (
            self._lock
        ):  # use a transaction or compare-and-set in a real backend
            state = fn(self.get(key))
            self._rows[key] = state.to_json()
            return state

    def put(self, key: str, state: BehaviorState) -> None:
        with self._lock:
            self._rows[key] = state.to_json()

    def delete(self, key: str) -> None:
        with self._lock:
            self._rows.pop(key, None)


engine = BehaviorEngine(state_store=JsonDictStore())
```

## Performance

Evaluation is in-process and allocation-light. Only patterns referenced by a policy are
evaluated, state snapshots are immutable and shared without copying, and the
deduplication window is bounded. A single engine processes tens of thousands of events per
second on one core.
