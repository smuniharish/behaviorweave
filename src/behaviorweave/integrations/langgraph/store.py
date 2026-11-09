"""Keep behavior state in a LangGraph ``BaseStore``."""

from __future__ import annotations

import asyncio
import threading
import zlib
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from langgraph.store.base import BaseStore

from ...errors import PolicyConfigurationError, StateStoreError
from ...state import BehaviorState, BehaviorStateStore

__all__ = ["LangGraphBehaviorStateStore"]

_STRIPES = 64


class LangGraphBehaviorStateStore(BehaviorStateStore):
    """A [`BehaviorStateStore`][behaviorweave.BehaviorStateStore] backed by a LangGraph store.

    Behavior state lives next to the graph's long-term memory, in any ``BaseStore``:
    ``InMemoryStore``, ``AsyncPostgresStore``, ``AsyncSqliteStore``, or your own. States are
    stored as JSON documents under ``namespace``, one item per state key, without vector
    indexing.

    ``BaseStore`` has no compare-and-set operation, so `update` is serialized by locks held in
    this object: it is atomic among the tasks, threads, and event loops of one process that
    share this instance. Run one instance per backing store, or, when several processes share
    a database, use a [`BehaviorStateStore`][behaviorweave.BehaviorStateStore] with
    transactional updates instead (see the Postgres and Redis examples).

    Args:
        store: The LangGraph store that holds the states. Its lifecycle stays with you;
            `close` does not close it.
        namespace: Namespace of the state items. Labels must be non-empty and must not
            contain periods.
        ttl: Optional lifetime of each state, refreshed on every write. Requires a store that
            supports TTL.

    Raises:
        PolicyConfigurationError: If ``store`` is not a ``BaseStore``, ``namespace`` is
            invalid, or ``ttl`` is not positive or the store does not support TTL.
    """

    def __init__(
        self,
        store: BaseStore,
        *,
        namespace: tuple[str, ...] = ("behaviorweave", "state"),
        ttl: timedelta | None = None,
    ) -> None:
        if not isinstance(store, BaseStore):
            raise PolicyConfigurationError(
                f"store must be a langgraph BaseStore, not {type(store).__name__}"
            )
        if not namespace or any(
            not isinstance(label, str) or not label or "." in label for label in namespace
        ):
            raise PolicyConfigurationError(
                "namespace must be a non-empty tuple of non-empty labels without periods"
            )
        options: dict[str, Any] = {}
        if ttl is not None:
            if ttl <= timedelta(0):
                raise PolicyConfigurationError("ttl must be a positive timedelta")
            if not store.supports_ttl:
                raise PolicyConfigurationError(f"{type(store).__name__} does not support TTL")
            options["ttl"] = ttl.total_seconds() / 60
        self.store = store
        self.namespace = namespace
        self._options = options
        self._locks = tuple(threading.Lock() for _ in range(_STRIPES))

    async def get(self, key: str) -> BehaviorState | None:
        """Return the state stored under ``key``, or ``None`` when absent or expired."""
        item = await self.store.aget(self.namespace, key)
        return None if item is None else BehaviorState.from_dict(item.value)

    async def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState:
        """Atomically replace the state under ``key`` with ``fn(current)`` and return it.

        Raises:
            StateStoreError: If ``fn`` does not return a ``BehaviorState``.
        """
        lock = self._locks[zlib.crc32(key.encode()) % _STRIPES]
        await _acquire(lock)
        try:
            updated = fn(await self.get(key))
            if not isinstance(updated, BehaviorState):
                raise StateStoreError("update function must return a BehaviorState")
            value = updated.to_dict()
            await self.store.aput(self.namespace, key, value, index=False, **self._options)
            return BehaviorState.from_dict(value)
        finally:
            lock.release()

    async def put(self, key: str, state: BehaviorState) -> None:
        """Store ``state`` under ``key``, replacing any existing state.

        Raises:
            StateStoreError: If ``state`` is not a ``BehaviorState``.
        """
        if not isinstance(state, BehaviorState):
            raise StateStoreError("state must be a BehaviorState")
        await self.store.aput(self.namespace, key, state.to_dict(), index=False, **self._options)

    async def delete(self, key: str) -> None:
        """Remove the state stored under ``key``, if any."""
        await self.store.adelete(self.namespace, key)


async def _acquire(lock: threading.Lock) -> None:
    # A thread lock, unlike an asyncio lock, works across event loops. Contended acquisition
    # waits in a worker thread so the event loop keeps running the lock holder.
    if lock.acquire(blocking=False):
        return
    waiter = asyncio.ensure_future(asyncio.to_thread(lock.acquire))
    try:
        await asyncio.shield(waiter)
    except asyncio.CancelledError:
        waiter.add_done_callback(lambda _: lock.release())
        raise
