# Extension contracts

## State store

```python
from behaviorweave import InMemoryBehaviorStateStore
from behaviorweave.testing import BehaviorStateStoreContract


class TestCustomBackend(BehaviorStateStoreContract):
    async def make_store(self):
        return InMemoryBehaviorStateStore()


TestCustomBackend().test_concurrent_updates_of_one_key_are_serialized()
```

Replace the factory with a fresh, ready backend; the contract closes it after each test.
Override `run_scenario` if the driver needs a particular event loop.

Reference PostgreSQL/Redis stores and live contract tests are in the
[repository](https://github.com/smuniharish/behaviorweave/tree/master/examples).
Validate expiry separately and inject independent backend clients to test replica races.

## Pattern

Implement `pattern_id`, `matches(event)`, and `async observe(event, store)`.
Use `dataclasses.replace` so engine cooldown/emission fields survive. Use an unambiguous,
scope-qualified key; never depend on private built-in key layouts.

Subclass `PatternContract`; implement `make_pattern()` and `make_event(scope, index)`.
Make events that match the custom pattern. The inherited tests check determinism, duplicate
delivery, scope isolation, and observation consistency.

## Audit

Subclass `AuditSink`. The record includes the original event, winning pattern observation,
state snapshot, and returned decision. Event metadata can contain raw arguments: redact
before the event enters the engine. Flush/close resources you own, not injected shared clients.
