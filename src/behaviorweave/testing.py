"""Conformance tests for custom state stores and patterns.

Subclass a contract in a test module, implement its factory methods, and your test runner
collects one test per promise in the contract:

```python
from behaviorweave.testing import BehaviorStateStoreContract


class TestMyStore(BehaviorStateStoreContract):
    async def make_store(self):
        store = MyStore(dsn)
        await store.truncate()  # every test starts from an empty store
        return store
```

The tests are plain synchronous methods that raise `AssertionError` with a descriptive
message, so they run under pytest, or under unittest when the subclass also inherits
``unittest.TestCase``. Neither pytest nor an async plugin is required.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .errors import StateStoreError
from .patterns import PatternObservation
from .state import BehaviorState

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

    from .events import BehaviorEvent
    from .patterns import Pattern
    from .state import BehaviorStateStore

__all__ = ["BehaviorStateStoreContract", "PatternContract"]

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _key() -> str:
    return f"contract:{uuid4().hex}"


def _rich_state(scope: str = "contract-scope") -> BehaviorState:
    return BehaviorState(
        pattern_id="contract.pattern",
        scope=scope,
        count=3,
        first_seen=_EPOCH,
        last_seen=_EPOCH + timedelta(seconds=5),
        previous_fingerprint="previous",
        current_fingerprint="current",
        event_count=4,
        intervention_history=("policy-a",),
        cooldowns={"policy-a": _EPOCH + timedelta(minutes=1)},
        seen_event_ids=("event-1", "event-2"),
        emissions=(("event-2", "policy-a", 3, "reason"),),
        metadata={"nested": {"values": [1, 2]}},
        version=7,
    )


def _advance(current: BehaviorState | None) -> BehaviorState:
    if current is None:
        return BehaviorState(pattern_id="contract.pattern", scope="contract-scope", count=1)
    return BehaviorState(
        pattern_id=current.pattern_id,
        scope=current.scope,
        count=current.count + 1,
        version=current.version + 1,
    )


class _Contract:
    def run_scenario(self, scenario: Coroutine[Any, Any, None]) -> None:
        """Run one scenario to completion; the default is ``asyncio.run``."""
        asyncio.run(scenario)


class BehaviorStateStoreContract(_Contract, ABC):
    """Tests every promise a [`BehaviorStateStore`][behaviorweave.BehaviorStateStore] makes.

    Each test calls `make_store` for a new, empty store, runs one scenario on it, and closes
    it. Override `run_scenario` to run scenarios on a specific event loop.
    """

    #: Number of concurrent updates of one key in the atomicity test.
    concurrency: int = 32

    @abstractmethod
    async def make_store(self) -> BehaviorStateStore:
        """Return a new, empty, ready-to-use store."""

    def test_get_of_a_missing_key_returns_none(self) -> None:
        """A key that was never written has no state."""

        async def scenario(store: BehaviorStateStore) -> None:
            state = await store.get(_key())
            _check(state is None, f"expected None for a missing key, got {state!r}")

        self._run(scenario)

    def test_put_then_get_round_trips_every_field(self) -> None:
        """A stored state is returned with every field intact."""

        async def scenario(store: BehaviorStateStore) -> None:
            key, state = _key(), _rich_state()
            await store.put(key, state)
            fetched = await store.get(key)
            _check(fetched == state, f"expected {state!r}, got {fetched!r}")

        self._run(scenario)

    def test_put_replaces_the_existing_state(self) -> None:
        """Writing a key twice keeps only the latest state."""

        async def scenario(store: BehaviorStateStore) -> None:
            key = _key()
            await store.put(key, _rich_state())
            latest = _advance(None)
            await store.put(key, latest)
            fetched = await store.get(key)
            _check(fetched == latest, f"expected the latest state {latest!r}, got {fetched!r}")

        self._run(scenario)

    def test_put_rejects_a_value_that_is_not_a_state(self) -> None:
        """``put`` raises ``StateStoreError`` for a value that is not a ``BehaviorState``."""

        async def scenario(store: BehaviorStateStore) -> None:
            try:
                await store.put(_key(), {"count": 1})  # pyrefly: ignore[bad-argument-type]
            except StateStoreError:
                return
            raise AssertionError("put accepted a value that is not a BehaviorState")

        self._run(scenario)

    def test_keys_are_isolated(self) -> None:
        """Writing one key never changes another."""

        async def scenario(store: BehaviorStateStore) -> None:
            first, second = _key(), _key()
            await store.put(first, _rich_state("first"))
            await store.update(second, _advance)
            fetched = await store.get(first)
            _check(fetched == _rich_state("first"), f"another key's write changed {fetched!r}")

        self._run(scenario)

    def test_update_passes_none_for_a_missing_key_and_stores_the_result(self) -> None:
        """``update`` starts from ``None`` and returns exactly what it stored."""

        async def scenario(store: BehaviorStateStore) -> None:
            key = _key()
            seen: list[BehaviorState | None] = []

            def fn(current: BehaviorState | None) -> BehaviorState:
                seen.append(current)
                return _advance(current)

            returned = await store.update(key, fn)
            _check(seen[-1:] == [None], f"fn received {seen!r} for a missing key")
            fetched = await store.get(key)
            _check(returned == fetched, f"update returned {returned!r} but stored {fetched!r}")
            _check(returned.count == 1, f"expected count 1, got {returned.count}")

        self._run(scenario)

    def test_update_receives_the_current_state(self) -> None:
        """``update`` passes the stored state to ``fn``."""

        async def scenario(store: BehaviorStateStore) -> None:
            key, state = _key(), _rich_state()
            await store.put(key, state)
            seen: list[BehaviorState | None] = []

            def fn(current: BehaviorState | None) -> BehaviorState:
                seen.append(current)
                return _advance(current)

            await store.update(key, fn)
            _check(seen[-1:] == [state], f"fn received {seen!r}, expected {state!r}")

        self._run(scenario)

    def test_update_rejects_a_result_that_is_not_a_state(self) -> None:
        """A non-state result raises ``StateStoreError`` and leaves the state unchanged."""

        async def scenario(store: BehaviorStateStore) -> None:
            key, state = _key(), _rich_state()
            await store.put(key, state)
            try:
                await store.update(key, lambda _: None)  # pyrefly: ignore[bad-argument-type]
            except StateStoreError:
                pass
            else:
                raise AssertionError("update accepted a result that is not a BehaviorState")
            fetched = await store.get(key)
            _check(fetched == state, f"a rejected update changed the state to {fetched!r}")

        self._run(scenario)

    def test_concurrent_updates_of_one_key_are_serialized(self) -> None:
        """Concurrent updates of one key never lose a write."""

        async def scenario(store: BehaviorStateStore) -> None:
            key = _key()
            await asyncio.gather(*(store.update(key, _advance) for _ in range(self.concurrency)))
            fetched = await store.get(key)
            count = None if fetched is None else fetched.count
            _check(
                count == self.concurrency,
                f"expected count {self.concurrency} after concurrent updates, got {count}",
            )

        self._run(scenario)

    def test_delete_removes_the_state_and_tolerates_missing_keys(self) -> None:
        """``delete`` removes a state; deleting a missing key is not an error."""

        async def scenario(store: BehaviorStateStore) -> None:
            key = _key()
            await store.put(key, _rich_state())
            await store.delete(key)
            await store.delete(key)
            fetched = await store.get(key)
            _check(fetched is None, f"expected None after delete, got {fetched!r}")

        self._run(scenario)

    def _run(self, scenario: Callable[[BehaviorStateStore], Awaitable[None]]) -> None:
        async def body() -> None:
            store = await self.make_store()
            try:
                await scenario(store)
            finally:
                await store.close()

        self.run_scenario(body())


class PatternContract(_Contract, ABC):
    """Tests every promise a [`Pattern`][behaviorweave.Pattern] makes to the engine.

    Implement `make_pattern`, `make_event`, and `make_store`. `make_event` returns a
    distinct event that the pattern matches for each ``index``; consecutive indexes must
    form a sequence the pattern accepts.
    """

    @abstractmethod
    def make_pattern(self) -> Pattern:
        """Return the pattern under test."""

    @abstractmethod
    def make_event(self, scope: str, index: int) -> BehaviorEvent:
        """Return the ``index``-th event, in ``scope``, of a sequence the pattern matches."""

    async def make_store(self) -> BehaviorStateStore:
        """Return a new, empty store; the default is an in-memory store."""
        from .state import InMemoryBehaviorStateStore

        return InMemoryBehaviorStateStore()

    def test_pattern_id_is_a_non_empty_string(self) -> None:
        """Policies reference a pattern by a non-empty string ``pattern_id``."""
        pattern_id = getattr(self.make_pattern(), "pattern_id", None)
        _check(
            isinstance(pattern_id, str) and bool(pattern_id),
            f"pattern_id must be a non-empty string, got {pattern_id!r}",
        )

    def test_matches_the_events_it_observes(self) -> None:
        """The pattern matches every event of its sequence."""
        pattern = self.make_pattern()
        for index in range(3):
            event = self.make_event("contract-scope", index)
            _check(pattern.matches(event), f"pattern does not match {event!r}")

    def test_observation_describes_the_event(self) -> None:
        """An observation carries the pattern ID, scope, and resulting state."""

        async def scenario(pattern: Pattern, store: BehaviorStateStore) -> None:
            observation = await pattern.observe(self.make_event("contract-scope", 0), store)
            _check(
                isinstance(observation, PatternObservation),
                f"observe returned {observation!r}, not a PatternObservation",
            )
            _check(
                observation.pattern_id == pattern.pattern_id,
                f"observation pattern_id {observation.pattern_id!r} differs from the pattern's",
            )
            _check(observation.scope == "contract-scope", f"wrong scope {observation.scope!r}")
            _check(observation.accepted, "the first observation of an event was not accepted")
            _check(
                observation.count == observation.state.count,
                "observation count differs from its state's count",
            )
            _check(bool(observation.reason), "observation has an empty reason")

        self._run(scenario)

    def test_redelivered_events_leave_the_state_unchanged(self) -> None:
        """Observing the same ``event_id`` twice is not accepted and keeps the count."""

        async def scenario(pattern: Pattern, store: BehaviorStateStore) -> None:
            event = self.make_event("contract-scope", 0)
            first = await pattern.observe(event, store)
            again = await pattern.observe(event, store)
            _check(not again.accepted, "a redelivered event was accepted")
            _check(
                again.count == first.count,
                f"a redelivered event changed the count from {first.count} to {again.count}",
            )

        self._run(scenario)

    def test_scopes_are_isolated(self) -> None:
        """Events in one scope never change another scope's count."""

        async def scenario(pattern: Pattern, store: BehaviorStateStore) -> None:
            for index in range(3):
                await pattern.observe(self.make_event("contract-a", index), store)
            other = await pattern.observe(self.make_event("contract-b", 0), store)
            empty = await self.make_store()
            try:
                fresh = await pattern.observe(self.make_event("contract-c", 0), empty)
            finally:
                await empty.close()
            _check(
                other.count == fresh.count,
                f"another scope's events changed the count to {other.count}, not {fresh.count}",
            )

        self._run(scenario)

    def test_observation_is_deterministic(self) -> None:
        """The same events in the same order produce the same observations."""

        async def scenario(pattern: Pattern, store: BehaviorStateStore) -> None:
            other = await self.make_store()
            try:
                for index in range(4):
                    event = self.make_event("contract-scope", index)
                    first = await pattern.observe(event, store)
                    second = await pattern.observe(event, other)
                    _check(
                        (first.count, first.reason, first.fingerprint)
                        == (second.count, second.reason, second.fingerprint),
                        f"observations differ for {event!r}: {first!r} and {second!r}",
                    )
            finally:
                await other.close()

        self._run(scenario)

    def _run(self, scenario: Callable[[Pattern, BehaviorStateStore], Awaitable[None]]) -> None:
        async def body() -> None:
            store = await self.make_store()
            try:
                await scenario(self.make_pattern(), store)
            finally:
                await store.close()

        self.run_scenario(body())
