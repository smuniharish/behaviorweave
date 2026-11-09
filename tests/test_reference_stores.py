"""The reference PostgreSQL and Redis state stores in ``examples/`` honor the store contract.

They run against live services. Set ``BEHAVIORWEAVE_POSTGRES_URL`` and
``BEHAVIORWEAVE_REDIS_URL`` to enable them; CI provides both.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Coroutine
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from behaviorweave import BehaviorState, BehaviorStateStore, StateStoreError
from behaviorweave.testing import BehaviorStateStoreContract

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

POSTGRES_URL = os.environ.get("BEHAVIORWEAVE_POSTGRES_URL")
REDIS_URL = os.environ.get("BEHAVIORWEAVE_REDIS_URL")

needs_postgres = pytest.mark.skipif(not POSTGRES_URL, reason="set BEHAVIORWEAVE_POSTGRES_URL")
needs_redis = pytest.mark.skipif(not REDIS_URL, reason="set BEHAVIORWEAVE_REDIS_URL")


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    # psycopg's async driver needs a selector event loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(scenario, loop_factory=loop_factory)


async def _postgres(**options: Any) -> BehaviorStateStore:
    from postgres_state_store import PostgresBehaviorStateStore

    assert POSTGRES_URL is not None
    store = await PostgresBehaviorStateStore.connect(POSTGRES_URL, **options)
    await store.truncate()
    return store


async def _redis(**options: Any) -> BehaviorStateStore:
    from redis_state_store import RedisBehaviorStateStore

    assert REDIS_URL is not None
    store = await RedisBehaviorStateStore.connect(REDIS_URL, **options)
    await store.truncate()
    return store


@needs_postgres
class TestPostgresStoreContract(BehaviorStateStoreContract):
    async def make_store(self) -> BehaviorStateStore:
        return await _postgres()

    def run_scenario(self, scenario: Coroutine[Any, Any, None]) -> None:
        _run(scenario)


@needs_redis
class TestRedisStoreContract(BehaviorStateStoreContract):
    async def make_store(self) -> BehaviorStateStore:
        return await _redis()

    def run_scenario(self, scenario: Coroutine[Any, Any, None]) -> None:
        _run(scenario)


def _expiry_scenario(factory: Any) -> Coroutine[Any, Any, None]:
    async def scenario() -> None:
        store = await factory(ttl=timedelta(milliseconds=500))
        try:
            await store.put("expiring", BehaviorState(pattern_id="p", scope="s"))
            assert await store.get("expiring") is not None
            await asyncio.sleep(1.2)
            assert await store.get("expiring") is None
            updated = await store.update(
                "expiring",
                lambda current: BehaviorState(
                    pattern_id="p", scope="s", count=0 if current is None else current.count + 1
                ),
            )
            assert updated.count == 0
        finally:
            await store.close()

    return scenario()


@needs_postgres
def test_postgres_states_expire() -> None:
    _run(_expiry_scenario(_postgres))


@needs_redis
def test_redis_states_expire() -> None:
    _run(_expiry_scenario(_redis))


@pytest.mark.parametrize(
    "factory",
    [pytest.param(_postgres, marks=needs_postgres), pytest.param(_redis, marks=needs_redis)],
)
def test_ttl_must_be_positive(factory: Any) -> None:
    with pytest.raises(StateStoreError, match="ttl must be a positive timedelta"):
        _run(factory(ttl=timedelta(0)))


@pytest.mark.parametrize(
    "factory",
    [pytest.param(_postgres, marks=needs_postgres), pytest.param(_redis, marks=needs_redis)],
)
def test_independent_clients_serialize_updates(factory: Any) -> None:
    async def scenario() -> None:
        first, second = await factory(), await factory()
        try:

            def advance(current: BehaviorState | None) -> BehaviorState:
                state = current or BehaviorState(pattern_id="p", scope="replicas")
                return replace(state, count=state.count + 1)

            await asyncio.gather(
                *(
                    client.update("replica-race", advance)
                    for _ in range(16)
                    for client in (first, second)
                )
            )
            stored = await first.get("replica-race")
            assert stored is not None
            assert stored.count == 32
        finally:
            await first.close()
            await second.close()

    _run(scenario())
