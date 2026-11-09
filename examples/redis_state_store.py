"""A reference Redis ``BehaviorStateStore``, shared by every process that uses the server.

Used by ``17_redis_state_store.py`` and verified against
``behaviorweave.testing.BehaviorStateStoreContract`` in ``tests/test_reference_stores.py``.
Copy it into your application and adapt the key layout to your conventions.

Each state is one JSON string. ``update`` is an optimistic ``WATCH``/``MULTI`` transaction:
when another client changes the key first, the transaction is discarded and ``fn`` runs again
on the newer state, so only the result of the final invocation is committed. Expiry uses
Redis's own key TTL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any, Self

from redis.asyncio import Redis
from redis.exceptions import WatchError

from behaviorweave import BehaviorState, BehaviorStateStore, StateStoreError


class RedisBehaviorStateStore(BehaviorStateStore):
    """Keep behavior state in Redis.

    Args:
        client: A ``redis.asyncio.Redis`` client. The store closes it only when it was
            created by `connect`.
        prefix: Prefix of every key the store writes.
        ttl: Optional positive lifetime of each state, refreshed on every write.
    """

    def __init__(
        self,
        client: Redis,
        *,
        prefix: str = "behaviorweave:state:",
        ttl: timedelta | None = None,
    ) -> None:
        if ttl is not None and ttl <= timedelta(0):
            raise StateStoreError("ttl must be a positive timedelta")
        self._client = client
        self._prefix = prefix
        self._ttl = ttl
        self._owns_client = False

    @classmethod
    async def connect(cls, url: str, **options: Any) -> Self:
        """Connect to the Redis server at ``url`` and return a store."""
        client = Redis.from_url(url)
        store = cls(client, **options)
        store._owns_client = True
        try:
            await client.ping()
        except BaseException:
            await client.aclose()
            raise
        return store

    async def truncate(self) -> None:
        """Remove every state under the store's prefix."""
        keys = [key async for key in self._client.scan_iter(match=f"{self._prefix}*")]
        if keys:
            await self._client.delete(*keys)

    async def get(self, key: str) -> BehaviorState | None:
        """Return the state stored under ``key``, or ``None`` when absent or expired."""
        raw = await self._client.get(self._prefix + key)
        return None if raw is None else BehaviorState.from_json(raw)

    async def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState:
        """Atomically replace the state under ``key`` with ``fn(current)`` and return it."""
        name = self._prefix + key
        async with self._client.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(name)
                    raw = await pipe.get(name)
                    updated = fn(None if raw is None else BehaviorState.from_json(raw))
                    if not isinstance(updated, BehaviorState):
                        raise StateStoreError("update function must return a BehaviorState")
                    pipe.multi()
                    pipe.set(name, updated.to_json(), px=self._ttl)
                    await pipe.execute()
                except WatchError:
                    continue
                return BehaviorState.from_json(updated.to_json())

    async def put(self, key: str, state: BehaviorState) -> None:
        """Store ``state`` under ``key``, replacing any existing state."""
        if not isinstance(state, BehaviorState):
            raise StateStoreError("state must be a BehaviorState")
        await self._client.set(self._prefix + key, state.to_json(), px=self._ttl)

    async def delete(self, key: str) -> None:
        """Remove the state stored under ``key``, if any."""
        await self._client.delete(self._prefix + key)

    async def close(self) -> None:
        """Close the client if `connect` created it."""
        if self._owns_client:
            await self._client.aclose()
