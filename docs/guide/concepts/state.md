# State and concurrency

Patterns keep an immutable `BehaviorState` per scope and pattern history. It records counts,
timestamps, identities, policy cooldowns, once-only emissions, and the 256 most recent event
IDs. Keys are opaque: custom backends must store them verbatim.

## Default store

`InMemoryBehaviorStateStore` is safe across threads and event loops, process-local, and lost
on restart. Its optional TTL refreshes on writes, never on reads.

```python
from datetime import timedelta
from behaviorweave import BehaviorEngine, InMemoryBehaviorStateStore

store = InMemoryBehaviorStateStore(ttl=timedelta(hours=24))
engine = BehaviorEngine(state_store=store)
print(await store.clear("finished-thread"))  # 0
print(await store.purge_expired())  # 0
await engine.close()
```

## Durable backends

Subclass the `BehaviorStateStore` ABC and implement async `get`, `update`, `put`, and `delete`.
`close` is an optional async lifecycle hook. `update(key, fn)` must serialize updates of one
key across **every process** that shares the backend. `fn` is synchronous and pure; optimistic
implementations may invoke it repeatedly, committing only the final result.

All writes must reject non-`BehaviorState` values with `StateStoreError`. Reads and returned
updates must be detached snapshots; mutating nested metadata must not change stored values.
Never return an expired entry. `BehaviorState.to_json()` and `from_json()` round-trip state.

Reference implementations:

- [PostgreSQL](https://github.com/smuniharish/behaviorweave/blob/master/examples/postgres_state_store.py):
  JSONB rows and transaction-scoped advisory locks, including absent keys.
- [Redis](https://github.com/smuniharish/behaviorweave/blob/master/examples/redis_state_store.py):
  JSON strings and optimistic WATCH/MULTI transactions.
- [LangGraph BaseStore](../../integrations/langgraph.md#reuse-a-langgraph-store):
  reuse application memory/storage with `LangGraphBehaviorStateStore`.

The LangGraph adapter serializes updates **within one adapter instance**. It is not a
distributed compare-and-swap implementation; share one adapter per backend namespace in a
process, or choose the PostgreSQL/Redis reference implementation for replicas.

## Guarantees and lifecycle

Atomic updates prevent lost counts, double-counted redeliveries, and duplicate once-only
emissions. The retained event-ID window bounds replay history; older redeliveries may count
again. Per-identity frequency histories grow with identity cardinality: use a TTL and clear
finished scopes in long-lived services.

Use `async with BehaviorEngine(...) as engine` or `await engine.close()` to flush/close the
audit sink and state store. An engine owns this lifecycle: when sharing a backend client,
keep client ownership in the application and implement the store's `close` accordingly.

Validate a backend by subclassing `behaviorweave.testing.BehaviorStateStoreContract` and
implementing `async make_store()`; see [testing](../how-to/testing.md).
