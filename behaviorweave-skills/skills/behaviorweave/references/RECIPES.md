# Async recipes

Use `await` within your application's async entry point or notebook.

## Nudge, then stop

```python
from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule

engine = BehaviorEngine(
    policies=[
        PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
        PolicyRule("stop", "repeated_tool_call", 3, InterventionType.STOP),
    ]
)
kinds = []
for _ in range(3):
    decision = await engine.process(BehaviorEvent.tool_call("lookup", scope="thread"))
    kinds.append(decision.intervention.kind.value)
print(kinds)  # ['noop', 'nudge', 'stop']
await engine.close()
```

## Guard an agent

<!-- skip-snippet: host supplies a configured model and tools -->
```python
from langchain.agents import create_agent
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware

middleware = BehaviorWeaveMiddleware(engine, on_decision=notify_operator)
agent = create_agent(model, tools, middleware=[middleware])
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Investigate the alarm."}]},
    config={"configurable": {"thread_id": "incident-42"}},
)
```

Keep operator side effects idempotent by checking `decision.duplicate`. Hooks that call
LangGraph `interrupt()` must run on duplicates so resume works.

## Durable state and audit

Use `LangGraphBehaviorStateStore` to reuse a BaseStore within one process. For replicas,
use a backend with atomic per-key transactions, such as the PostgreSQL/Redis
[reference implementations](https://github.com/smuniharish/behaviorweave/tree/master/examples).
Inject clients/pools and keep lifecycle ownership explicit.

For in-memory audit, use `InMemoryAuditSink`. For agxai, pass `AgxaiAuditSink(runtime)`:
inside an instrumented run, interventions become evidence and decisions. Combine sinks with
`CompositeAuditSink`, for example with `OpenTelemetryMetricsSink` for decision metrics.

When a conversation ends, call `await engine.expire_scope(scope)` to release its history,
including middleware halts. Replay recorded events with `await engine.process_many(events)`;
keep their original event IDs so a retried batch is idempotent.

## agxai with an existing exporter

<!-- skip-snippet: graph and exporter belong to the application -->
```python
from behaviorweave.integrations.agxai import (
    BehaviorWeaveObservability,
    create_agxai_runtime,
    instrument_graph,
)

runtime = create_agxai_runtime(
    store=application_store,
    observability=BehaviorWeaveObservability(auditor, delegate=exporter),
    plugins=application_plugins,
)
graph = instrument_graph(compiled_graph, runtime=runtime)
try:
    result = await graph.ainvoke(inputs)
finally:
    await runtime.close()
```

Captured-event decisions are observational. Enforce at the graph/tool boundary before an
action. Canonical execution spans and semantic audit records are different data surfaces.
