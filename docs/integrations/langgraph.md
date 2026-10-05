# LangGraph

LangGraph owns execution, routing, persistence, and interrupts. BehaviorWeave observes node
executions and multi-agent activity and returns decisions; your graph decides how to route
on them.

## Guard a loop with conditional edges

Report node executions with
[`LangGraphEventAdapter`][behaviorweave.integrations.langgraph.LangGraphEventAdapter] and
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


def work(state: LoopState) -> dict[str, object]:
    decision = engine.process(adapter.node("work", scope="thread-7"))
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
result = builder.compile().invoke({"steps": 0, "stopped_by": None})
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
    last = engine.process(adapter.handoff(source, target, scope="case-9"))
print(last.intervention.kind.value)  # redirect
```

For LangGraph Swarm, stream the swarm and report each change of active agent; see
[`05_langgraph_swarm.py`](../examples.md).

## Adapter reference

| Method | Event |
| --- | --- |
| `node(node_name, *, scope, metadata=None, event_id=None)` | `node_execution` |
| `tool(tool_name, *, scope, arguments=None, event_id=None)` | `tool_call` |
| `outcome(outcome, *, scope, node_name=None, event_id=None)` | `outcome` |
| `handoff(source_agent, target_agent, *, scope, event_id=None)` | `agent_handoff` |
| `delegation(source_agent, target_agent, *, scope, event_id=None)` | `delegation` |
