# LangGraph

LangGraph owns execution, routing, persistence, and interrupts. BehaviorWeave observes node
executions and multi-agent activity and returns decisions; your graph decides how to route
on them.

## Guard a loop with conditional edges

Report node executions with
[`LangGraphEventAdapter`](../api/index.md#behaviorweave.integrations.langgraph.LangGraphEventAdapter) and
route on terminal decisions:

```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph import LangGraphEventAdapter

adapter = LangGraphEventAdapter()
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "loop-guard", "repeated_node_execution", 4, InterventionType.STOP
        )
    ]
)


class LoopState(TypedDict):
    steps: int
    stopped_by: str | None


async def work(state: LoopState) -> dict[str, object]:
    decision = await engine.process(adapter.node("work", scope="thread-7"))
    stopped = (
        decision.intervention.policy
        if decision.intervention.kind.is_terminal
        else None
    )
    return {"steps": state["steps"] + 1, "stopped_by": stopped}


def route(state: LoopState) -> str:
    return END if state["stopped_by"] else "work"


builder = StateGraph(LoopState)
builder.add_node("work", work)
builder.add_edge(START, "work")
builder.add_conditional_edges("work", route)
result = await builder.compile().ainvoke({"steps": 0, "stopped_by": None})
print(result)  # {'steps': 4, 'stopped_by': 'loop-guard'}
```

Inside real nodes, take the scope from the run configuration: accept a `config`
parameter and use `config["configurable"]["thread_id"]`.

## Multi-agent handoffs and delegation

Report control transfers as handoffs or delegations. The built-in `oscillation` pattern
detects agents bouncing work back and forth, and `delegation_streak` detects repeated
delegation to the same agent:

```python
engine = BehaviorEngine(
    policies=[
        PolicyRule("ping-pong", "oscillation", 2, InterventionType.REDIRECT)
    ]
)
hops = [
    ("triage", "billing"),
    ("billing", "triage"),
    ("triage", "billing"),
    ("billing", "triage"),
]
last = None
for source, target in hops:
    last = await engine.process(adapter.handoff(source, target, scope="case-9"))
print(last.intervention.kind.value)  # redirect
```

For LangGraph Swarm, stream the swarm and report each change of active agent; see
[`05_langgraph_swarm.py`](../examples/index.md).

## Adapter reference

| Method | Event |
| --- | --- |
| `node(node_name, *, scope, metadata=None, event_id=None)` | `node_execution` |
| `tool(tool_name, *, scope, arguments=None, event_id=None)` | `tool_call` |
| `outcome(outcome, *, scope, node_name=None, event_id=None)` | `outcome` |
| `handoff(source_agent, target_agent, *, scope, event_id=None)` | `agent_handoff` |
| `delegation(source_agent, target_agent, *, scope, event_id=None)` | `delegation` |

## Reuse a LangGraph store

`LangGraphBehaviorStateStore` accepts any `BaseStore`, a namespace, and an optional TTL.
The backend must support TTL if you request it. Async operations pass through to the
backend without taking over its lifecycle.

```python
from langgraph.store.memory import InMemoryStore
from behaviorweave.integrations.langgraph import LangGraphBehaviorStateStore

backend = InMemoryStore()
state_store = LangGraphBehaviorStateStore(
    backend, namespace=("support", "behavior")
)
engine = BehaviorEngine(state_store=state_store)
```

Locks serialize updates within one adapter instance only. Share that instance in a process.
For cross-process atomicity, use the PostgreSQL or Redis reference store; see
[state and concurrency](../guide/concepts/state.md). The
[Postgres BaseStore example](https://github.com/smuniharish/behaviorweave/blob/master/examples/18_langgraph_store.py)
shows backend setup, TTL, namespace isolation, and cleanup.
