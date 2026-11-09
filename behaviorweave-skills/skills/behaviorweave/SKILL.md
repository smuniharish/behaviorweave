---
name: behaviorweave
description: "Integrate, configure, test, and debug BehaviorWeave in LangChain, LangGraph, Deep Agents, and MCP applications. Use when agents repeat tool calls, loop on nodes, accumulate failures or retries, delegate repeatedly, or hand work back and forth; add explicit nudge, escalation, human-review, pause, or stop policies. Also use for agxai provenance audits, middleware halts, thresholds, cooldowns, and once-only rules. Not for model-based behavior classification or generic monitoring. For new storage, pattern, or audit implementations use behaviorweave-extend."
license: Apache-2.0
compatibility: Python 3.12 through 3.15 with behaviorweave 1.1.x. Setup checks run offline in the application's environment.
metadata:
  version: "1.1.0"
  documentation: "https://behaviorweave.readthedocs.io"
---

# BehaviorWeave

BehaviorWeave observes events and returns typed decisions. The host or LangChain middleware
applies them; the engine never secretly controls execution.

## Workflow

1. Run `python scripts/verify_setup.py` from this skill's directory in the project's Python
   environment. Resolve every `FAIL` before integrating.
2. Locate tool boundaries, graph nodes, outcomes, and handoffs. Choose a stable,
   tenant-qualified thread/run scope.
3. Use an existing detector before creating one:
   - `repeated_tool_call`: consecutive same tool and arguments.
   - `repeated_node_execution`: consecutive same node.
   - `failure_streak`, `retry_streak`, `success_streak`: consecutive outcomes.
   - `delegation_streak`: repeated delegation to one target.
   - `oscillation`: back-and-forth handoffs/delegations.
   - `event_frequency`: per-identity total budget.
4. Define `PolicyRule`s with explicit thresholds, priorities, cooldowns, and once-only rules.
5. Wire the host:
   - LangChain/Deep Agents: `BehaviorWeaveMiddleware(engine)` in `middleware`.
   - LangGraph: await `engine.process(adapter.node(...))`; route on the returned decision.
   - MCP: await processing inside async tool handlers.
   - agxai: `BehaviorWeaveObservability` or `AgxaiEventAdapter` for captured events;
     `AgxaiAuditSink` for semantic intervention records.
   - Metrics: `OpenTelemetryMetricsSink` (`otel` extra); combine sinks with
     `CompositeAuditSink`.
6. Await lifecycle operations. Use `async with BehaviorEngine(...)` or `await engine.close()`.
   Close application-owned agxai runtimes separately. When a conversation ends, release its
   history with `await engine.expire_scope(scope)`; replay batches with `process_many`.
7. Copy [the policy tests](assets/test_behavior_policy.py), adapt them, and run tests plus
   the setup check again.

## Rules

- **Async I/O, pure transforms.** Await processing, store operations, halt inspection/release,
  flush, and close. State-update callbacks and event adapters remain synchronous.
- **Reuse detectors.** Do not add prompt-only counters beside an existing built-in pattern.
- **Scope isolation.** Middleware defaults to `thread_id`; without it, configure `scope`.
- **Idempotency.** Reuse IDs only for redelivery. Skip duplicate external side effects,
  but never skip LangGraph `interrupt()`: resumed steps must call it again.
- **Persisted halts.** `await middleware.halted(scope)` inspects the engine store.
  `await middleware.release(scope)` explicitly lifts a halt before resuming.
- **Error visibility.** Invalid components/configuration raise `PolicyConfigurationError`;
  backend and hook failures propagate. Never replace them with no-op decisions.
- **Data boundaries.** Arguments are fingerprinted for identity but remain in event metadata
  for audit. Redact secrets before creating events.
- **Extension boundaries.** Subclass ABCs; configure public APIs, never patch installed code.
- **agxai customization.** Pass the host's config, registry, IDs, plugins, custom capture,
  store, exporter, attribution, explanation, disclosure policy, and capture policy through
  `create_agxai_runtime`.

## Human review

Use an `on_decision` hook and a LangGraph checkpointer. `human_review` can call `interrupt()`;
`stop`/`pause` block by default. A blocking outcome arrives after the tool runs and therefore
halts later calls. Release that persisted halt from the application before resuming.

## References

- [API](references/API.md): exact public entry points.
- [Recipes](references/RECIPES.md): async wiring and custom providers.
- [Troubleshooting](references/TROUBLESHOOTING.md): diagnosis by observed behavior.
