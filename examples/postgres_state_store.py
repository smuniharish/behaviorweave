"""A reference PostgreSQL ``BehaviorStateStore``, shared by every process that uses the database.

Used by ``16_postgres_state_store.py`` and verified against
``behaviorweave.testing.BehaviorStateStoreContract`` in ``tests/test_reference_stores.py``.
Copy it into your application and adapt the table layout to your conventions.

Each state is one JSONB row. ``update`` holds a transaction-scoped advisory lock on the key,
so concurrent updates of one key are serialized across every process, including updates of a
key that has no row yet. Expired rows are never returned and are overwritten in place.

psycopg's async connections need a selector event loop on Windows; run with
``asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)`` there.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any, LiteralString, Self

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from behaviorweave import BehaviorState, BehaviorStateStore, StateStoreError

_SELECT_LIVE = (
    "SELECT state FROM {table} WHERE key = %s AND (expires_at IS NULL OR expires_at > now())"
)


class PostgresBehaviorStateStore(BehaviorStateStore):
    """Keep behavior state in a PostgreSQL table.

    Args:
        pool: An open ``psycopg_pool.AsyncConnectionPool``. The store closes it only when it
            was created by `connect`.
        table: Name of the state table; `setup` creates it.
        ttl: Optional positive lifetime of each state, refreshed on every write.
    """

    def __init__(
        self,
        pool: AsyncConnectionPool[Any],
        *,
        table: str = "behaviorweave_state",
        ttl: timedelta | None = None,
    ) -> None:
        if ttl is not None and ttl <= timedelta(0):
            raise StateStoreError("ttl must be a positive timedelta")
        self._pool = pool
        self._table = sql.Identifier(table)
        self._ttl = ttl
        self._owns_pool = False

    @classmethod
    async def connect(cls, conninfo: str, **options: Any) -> Self:
        """Open a connection pool to ``conninfo``, create the table, and return a store."""
        pool = AsyncConnectionPool(conninfo, open=False, kwargs={"autocommit": True})
        store = cls(pool, **options)
        store._owns_pool = True
        try:
            await pool.open(wait=True)
            await store.setup()
        except BaseException:
            await pool.close()
            raise
        return store

    async def setup(self) -> None:
        """Create the state table if it does not exist."""
        await self._execute(
            "CREATE TABLE IF NOT EXISTS {table} ("
            "key text PRIMARY KEY, state jsonb NOT NULL, expires_at timestamptz)"
        )

    async def truncate(self) -> None:
        """Remove every state."""
        await self._execute("TRUNCATE {table}")

    async def get(self, key: str) -> BehaviorState | None:
        """Return the state stored under ``key``, or ``None`` when absent or expired."""
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute(self._query(_SELECT_LIVE), (key,))
            row = await cursor.fetchone()
        return None if row is None else BehaviorState.from_dict(row["state"])

    async def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState:
        """Atomically replace the state under ``key`` with ``fn(current)`` and return it."""
        async with self._pool.connection() as connection, connection.transaction():
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
            await cursor.execute(self._query(_SELECT_LIVE), (key,))
            row = await cursor.fetchone()
            updated = fn(None if row is None else BehaviorState.from_dict(row["state"]))
            if not isinstance(updated, BehaviorState):
                raise StateStoreError("update function must return a BehaviorState")
            await self._write(cursor, key, updated)
        return BehaviorState.from_dict(updated.to_dict())

    async def put(self, key: str, state: BehaviorState) -> None:
        """Store ``state`` under ``key``, replacing any existing state."""
        if not isinstance(state, BehaviorState):
            raise StateStoreError("state must be a BehaviorState")
        async with self._pool.connection() as connection:
            await self._write(connection.cursor(), key, state)

    async def delete(self, key: str) -> None:
        """Remove the state stored under ``key``, if any."""
        await self._execute("DELETE FROM {table} WHERE key = %s", (key,))

    async def close(self) -> None:
        """Close the connection pool if `connect` opened it."""
        if self._owns_pool:
            await self._pool.close()

    async def _write(self, cursor: Any, key: str, state: BehaviorState) -> None:
        await cursor.execute(
            self._query(
                "INSERT INTO {table} (key, state, expires_at) VALUES (%s, %s, now() + %s) "
                "ON CONFLICT (key) DO UPDATE "
                "SET state = EXCLUDED.state, expires_at = EXCLUDED.expires_at"
            ),
            (key, Jsonb(state.to_dict()), self._ttl),
        )

    async def _execute(self, statement: LiteralString, parameters: tuple[object, ...] = ()) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(self._query(statement), parameters)

    def _query(self, statement: LiteralString) -> sql.Composed:
        return sql.SQL(statement).format(table=self._table)
