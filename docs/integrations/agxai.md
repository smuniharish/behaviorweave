# agxai

[agxai](https://agxai.readthedocs.io/) records execution provenance, evidence, decisions,
attribution, and audience-safe explanations. BehaviorWeave decides what intervention to
request from observed behavior; agxai explains the recorded decision. Neither captures
private model reasoning.

## Customization

`create_agxai_runtime` exposes every agxai runtime setting and capability:

| Surface | Arguments |
| --- | --- |
| Identity | `application_id`, `tenant_id`, `graph_id` |
| Configuration and registry | `config` (`XAIConfig`), `registry` (`Registry`) |
| Semantic plugins and custom capture | `plugins`, `custom_state_capture` |
| Storage | `store` (`ProvenanceStore` ABC) |
| Exporters | `observability` (`ObservabilityProvider` ABC) |
| Attribution and explanation | `attribution`, `explanation` |
| Disclosure and capture policies | `policy`, `capture_policy` |

Omitted capabilities preserve the supplied registry's providers or agxai's defaults.
Invalid component types raise `PolicyConfigurationError`. Runtime ownership stays with the
application; always close it.

<!-- skip-snippet: graph and application providers are supplied by the host -->
```python
from agxai import XAIConfig
from behaviorweave.integrations.agxai import (
    create_agxai_runtime,
    instrument_graph,
)

runtime = create_agxai_runtime(
    config=XAIConfig(max_concurrency=8),
    application_id="support-bot",
    store=my_provenance_store,
    observability=my_exporter,
)
graph = instrument_graph(compiled_graph, runtime=runtime)
try:
    result = await graph.ainvoke(inputs)
finally:
    await runtime.close()
```

## Feed captured events into an engine

`BehaviorWeaveObservability(engine, delegate=..., scope=..., on_decision=...)` maps node,
tool, and run outcomes to behavior events, forwards **every** canonical event to `delegate`,
and calls the sync or async decision hook. The default scope is the thread ID, or run ID
when no thread is present. Use `scope` to customize isolation.

This is observational: a verdict does not block the captured execution. To enforce a policy,
use LangChain middleware or inspect `engine.process()` in the graph before the action.

## Record interventions as evidence and decisions

Pass `AgxaiAuditSink(runtime)` as an engine's `audit_sink`. Actionable, nonduplicate
interventions inside the current instrumented run become agxai evidence and decisions.
Outside a run nothing is recorded. Semantic records go to agxai's store/plugins; its
observability stream exports canonical execution events, not semantic records.

See the [complete agent example](https://github.com/smuniharish/behaviorweave/blob/master/examples/15_complete_agent_guard.py)
for a guard, semantic audit sink, captured-event auditor, and runtime lifecycle together.

## Map canonical events explicitly

`AgxaiEventAdapter.event` accepts a canonical event or its dumped mapping. Node and tool
success/failure statuses become outcomes; cancellation and interruption have no outcome.
The canonical ID becomes the event ID and default provenance reference. Only source, event
type, and sequence metadata are retained. Captured tools have no argument payload, so their
identity is the tool name, not tool-plus-arguments.

```python
from agxai import ExecutionContext, ToolExecution, ToolStatus
from agxai.core import ToolExecutionEvent
from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.agxai import AgxaiEventAdapter

context = ExecutionContext(
    application_id="support", tenant_id="local", graph_id="triage"
)
engine = BehaviorEngine(
    policies=[
        PolicyRule("outage", "failure_streak", 2, InterventionType.ESCALATE)
    ]
)
for sequence in range(2):
    event = ToolExecutionEvent(
        context=context,
        sequence=sequence,
        tool=ToolExecution(
            context=context,
            tool_id="crm",
            tool_name="crm",
            status=ToolStatus.FAILED,
        ),
    )
    decision = await engine.process(
        AgxaiEventAdapter().event(event, scope="audit")
    )
print(decision.intervention.kind.value)  # escalate
print(decision.explanation.provenance_ref is not None)  # True
```
