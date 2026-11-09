# Public API

## Core

- `BehaviorEngine(*, policies=(), patterns=None, state_store=None, audit_sink=None)`
- `await engine.process(event) -> InterventionDecision`
- `await engine.flush()`, `await engine.close()`, async context manager.
- `PolicyRule(policy_id, pattern_id, threshold, intervention, ...)`: use keyword arguments
  for optional priority, cooldown, once-only, severity, and message settings.
- `BehaviorEvent.tool_call(name, arguments=None, *, scope=..., ...)` and node/outcome,
  retry, handoff, delegation factories.
- `decision.actionable`, `.duplicate`, `.suppressed`, `.intervention`, `.explanation`.
- `decision.to_dict()` / `InterventionDecision.from_dict(data)` round-trip decisions.

## ABC extension points

- `Pattern`: `pattern_id`, pure `matches(event)`, async `observe(event, store)`.
- `BehaviorStateStore`: async `get`, `update(key, fn)`, `put`, `delete`; optional `close`.
- `AuditSink`: async `write(record)`; optional `flush`, `close`.
- `InMemoryAuditSink.records` inspects audit; async `clear` resets it.
- `InMemoryBehaviorStateStore(ttl=None, *, clock=None)`: async `clear(scope=None)` and
  `purge_expired`, in addition to the store contract.

The transform passed to `update` is synchronous and pure. An optimistic backend may invoke
it more than once. Keep state keys opaque.

## Integrations

`behaviorweave.integrations.langchain` exports:

- `BehaviorWeaveMiddleware(engine, *, scope=None, block_on=..., track_outcomes=True,
  on_decision=None, formatter=None, name=None)`.
- `await middleware.halted(scope)` and `await middleware.release(scope)`.
- `LangChainEventAdapter` and `default_guidance`.

`behaviorweave.integrations.langgraph` exports `LangGraphEventAdapter` and
`LangGraphBehaviorStateStore(store, *, namespace=("behaviorweave", "state"), ttl=None)`.
The latter serializes updates only within one adapter instance; host owns backend lifecycle.

`behaviorweave.integrations.agxai` exports:

- `create_agxai_runtime(*, config=None, registry=None, application_id="behaviorweave",
  tenant_id="default", graph_id="graph", plugins=(), custom_state_capture=None,
  store=None, observability=None, attribution=None, explanation=None, policy=None,
  capture_policy=None)`.
- `instrument_graph(graph, *, runtime=None)`.
- `AgxaiEventAdapter`, `AgxaiAuditSink(runtime)`.
- `BehaviorWeaveObservability(engine, *, delegate=None, scope=thread_scope,
  on_decision=None, adapter=None)`.

The observability hook receives `(canonical_event, decision)`; middleware's hook receives
`(decision, behavior_event)`. Both may be async. Formatters remain synchronous.

See the [generated API](https://behaviorweave.readthedocs.io/en/latest/api/) for full
signatures and the `behaviorweave.testing` contract ABCs.
