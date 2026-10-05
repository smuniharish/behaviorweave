# langgraph-xai

[`langgraph-xai`](https://pypi.org/project/langgraph-xai/) records provenance for LangGraph
executions: every node, tool call, and run outcome becomes a canonical, timestamped event.
BehaviorWeave consumes that provenance through langgraph-xai's public API. It never recreates
explainability data or captures private model reasoning.

## Instrument a graph

[`LangGraphXAIEventAdapter.instrument_graph`][behaviorweave.integrations.langgraph_xai.LangGraphXAIEventAdapter.instrument_graph]
wraps a compiled graph with `XAIRuntime.instrument`. Pass your own runtime so you can query
its provenance store and close it when you are done; otherwise the adapter creates one, which
is available as the instrumented graph's `runtime`.

<!-- skip-snippet: `graph` is your compiled LangGraph graph -->
```python
from langgraph_xai import XAIRuntime

from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter

runtime = XAIRuntime(
    application_id="support-bot", tenant_id="acme", graph_id="triage"
)
instrumented = LangGraphXAIEventAdapter.instrument_graph(graph, runtime=runtime)
instrumented.invoke({"messages": [...]})
```

## Map canonical events

[`LangGraphXAIEventAdapter.event`][behaviorweave.integrations.langgraph_xai.LangGraphXAIEventAdapter.event]
maps a canonical langgraph-xai event, either the model or its `model_dump()`, to a
`BehaviorEvent`:

| langgraph-xai event | BehaviorWeave event | Outcome |
| --- | --- | --- |
| `node.execution` | `node_execution` (node ID) | from the node status |
| `tool.execution` | `tool_call` (tool name) | from the tool status |
| `execution.completed` | `outcome` | `success` |
| `execution.failed` | `outcome` | `failure`, or none for a cancelled run |
| a BehaviorWeave event type name | that event type | explicit `outcome` |
| anything else | `custom` | none |

Node and tool statuses map to outcomes as follows:

| Status | Outcome |
| --- | --- |
| `completed` (node), `succeeded` (tool) | `success` |
| `failed`, `timed_out` (tool) | `failure` |
| `running`, `cancelled`, `interrupted` | none |

Cancellations and interruptions, such as a human-in-the-loop pause or a stream closed early,
are neither successes nor failures, so they never extend or reset a streak.

The canonical event `id` becomes the `event_id`, so replayed provenance records are
deduplicated, and it is the default `provenance_ref` that the engine copies into every
decision's explanation. Only a small, safe subset of the payload (source, event type, and
sequence number) is kept as metadata. langgraph-xai records tool executions without their
arguments, so a mapped tool call's identity is its tool name.

```python
from langgraph_xai import ExecutionContext, ToolExecution, ToolStatus
from langgraph_xai.core import ToolExecutionEvent

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter

context = ExecutionContext(
    application_id="support-bot", tenant_id="acme", graph_id="triage"
)


def failed_tool() -> ToolExecutionEvent:
    execution = ToolExecution(
        context=context,
        tool_id="crm",
        tool_name="crm_lookup",
        status=ToolStatus.FAILED,
    )
    return ToolExecutionEvent(context=context, sequence=1, tool=execution)


adapter = LangGraphXAIEventAdapter()
engine = BehaviorEngine(
    policies=[
        PolicyRule("crm-outage", "failure_streak", 2, InterventionType.ESCALATE)
    ]
)
decisions = [
    engine.process(adapter.event(failed_tool(), scope="audit"))
    for _ in range(2)
]
print(decisions[-1].intervention.kind.value)  # escalate
print(decisions[-1].explanation.provenance_ref is not None)  # True
```

## Post-run behavioral audit

Because langgraph-xai stores every tool execution, you can replay a finished run through an
audit engine, with each decision linked to its provenance record. Collect the run with
`XAIRuntime.collect_runs()`, query its tool executions, and close the runtime when you are
done:

```python
from typing import TypedDict

from langchain.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph_xai import ProvenanceStore, StoreFilter, XAIRuntime
from langgraph_xai.core import ToolExecutionEvent

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter


@tool
def crm_lookup(customer: str) -> str:
    """Look up one customer record."""
    return f"{customer}: active"


class Triage(TypedDict):
    customer: str
    notes: list[str]


def triage(state: Triage) -> dict[str, list[str]]:
    customer = {"customer": state["customer"]}
    return {"notes": [crm_lookup.invoke(customer) for _ in range(2)]}


builder = StateGraph(Triage)
builder.add_node("triage", triage)
builder.add_edge(START, "triage")
builder.add_edge("triage", END)

runtime = XAIRuntime(
    application_id="support-bot", tenant_id="acme", graph_id="triage"
)
graph = LangGraphXAIEventAdapter.instrument_graph(
    builder.compile(), runtime=runtime
)
with runtime.collect_runs() as runs:
    graph.invoke({"customer": "c-42", "notes": []})
(run,) = runs


async def audit() -> list[str]:
    store = runtime.registry.get(ProvenanceStore)
    query = StoreFilter(
        application_id="support-bot",
        tenant_id="acme",
        run_id=run.run_id,
        item_type=ToolExecutionEvent,
    )
    auditor = BehaviorEngine(
        policies=[
            PolicyRule(
                "busy-tool", "event_frequency", 2, InterventionType.WARNING
            )
        ]
    )
    adapter = LangGraphXAIEventAdapter()
    findings = []
    async for record in store.query(query):
        decision = auditor.process(adapter.event(record, scope="audit"))
        if decision.actionable:
            findings.append(decision.intervention.reason)
    return findings


print(runtime.run_sync(audit()))  # ["'crm_lookup' occurred 2 times"]
runtime.run_sync(runtime.close())
```

The flagship example, [`15_complete_agent_guard.py`](../examples.md), runs this audit after a
live agent run.
