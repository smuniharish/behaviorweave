---
name: behaviorweave-extend
description: "Implement, test, and review custom BehaviorWeave storage backends, patterns, and audit sinks using async ABCs. Use for distributed PostgreSQL/Redis state, LangGraph BaseStore adapters, atomic updates, custom deterministic detectors, and downstream agxai provider injection. Not for routine middleware configuration; use behaviorweave for that."
license: Apache-2.0
compatibility: Python 3.12 through 3.15 with behaviorweave 1.1.x. Contract tests need no pytest-specific API.
metadata:
  version: "1.1.0"
  documentation: "https://behaviorweave.readthedocs.io"
---

# Extend BehaviorWeave

## Workflow

1. Confirm a built-in pattern, existing state adapter, or agxai provider does not already
   satisfy the requirement. Prefer injection over a new abstraction.
2. Read [the contracts](references/CONTRACTS.md) and the actual ABC signatures.
3. Implement async I/O and synchronous pure transforms. Preserve idempotency, scope
   isolation, policy bookkeeping, and explicit lifecycle ownership.
4. Subclass `BehaviorStateStoreContract` or `PatternContract`; run all inherited tests.
   For distributed storage also test independent clients/processes against the real backend.
5. Run the package's lint, type, and relevant regression tests. Verify failures propagate.

## Non-negotiable invariants

- A store's `update` is atomic per key across all processes using the backend.
- Optimistic retries may re-run `fn`; only its final result commits.
- Invalid values raise `StateStoreError` without replacing valid state.
- Returned state is detached; expired data is never returned.
- Custom patterns preserve cooldowns/emissions and deduplicate retained event IDs.
- Audit sinks implement `async write(record)` and optional async flush/close.
- The LangGraph store adapter has instance-local locks, not distributed transactions.
- Inject configured clients/providers; never restrict downstream customization to a URL
  when the downstream package supports richer configuration.

## Downstream providers

`create_agxai_runtime` accepts config, registry, identity, plugins, custom capture, store,
observability, attribution, explanation, disclosure policy, and capture policy.
Subclass the corresponding agxai ABC rather than introducing a parallel interface.
Use `BehaviorWeaveObservability(delegate=...)` to preserve an existing exporter.
