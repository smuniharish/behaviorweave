# BehaviorWeave recipes

Complete patterns for common integration tasks. Recipes that need a live model or server are
marked; every other snippet runs as written.

## Guard a LangChain agent

Add the middleware to `create_agent` (Deep Agents accept the same `middleware=[...]`). Scope
comes from the `thread_id`:

<!-- skip-snippet: needs a provider-backed chat model -->
```python
from langchain.agents import create_agent

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware

engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "repeat-nudge",
            "repeated_tool_call",
            2,
            InterventionType.NUDGE,
            message="Reuse the result you already have.",
        ),
        PolicyRule("repeat-stop", "repeated_tool_call", 3, InterventionType.STOP),
    ]
)
agent = create_agent(model, tools, middleware=[BehaviorWeaveMiddleware(engine)])
agent.invoke(
    {"messages": [{"role": "user", "content": "Inspect ETCH-3."}]},
    config={"configurable": {"thread_id": "incident-42"}},
)
```

The second identical call returns the tool result with `[BehaviorWeave:nudge] ...` appended;
the third is refused before the tool runs.

## Test a guarded agent offline

Drive `create_agent` with a scripted chat model to test policies without a provider:

```python
from langchain.agents import create_agent
from langchain.messages import AIMessage
from langchain.tools import tool
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware


class ScriptedModel(GenericFakeChatModel):
    """Replays scripted messages and accepts tool binding."""

    def bind_tools(self, tools, **kwargs):
        return self


def call(call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "get_alarm", "args": {"machine": "ETCH-3"}, "id": call_id}],
    )


runs = []


@tool
def get_alarm(machine: str) -> str:
    """Return the current alarm for one machine."""
    runs.append(machine)
    return f"{machine}: chamber-pressure warning"


model = ScriptedModel(
    messages=iter([call("c1"), call("c2"), call("c3"), AIMessage(content="Done.")])
)
engine = BehaviorEngine(
    policies=[
        PolicyRule("repeat-nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
        PolicyRule("repeat-stop", "repeated_tool_call", 3, InterventionType.STOP),
    ]
)
agent = create_agent(model, [get_alarm], middleware=[BehaviorWeaveMiddleware(engine)])
result = agent.invoke(
    {"messages": [{"role": "user", "content": "Inspect ETCH-3."}]},
    config={"configurable": {"thread_id": "test-1"}},
)
tool_results = [m.text for m in result["messages"] if m.type == "tool"]
print(len(runs))  # 2
print(tool_results[2])  # [BehaviorWeave:stop] 'get_alarm' occurred 3 consecutive times
```

## Require approval before a tool runs

Raise from `on_decision` unless a reviewer approves. Decisions on tool calls are made before
the tool runs, so a rejected call never runs. The agent needs a checkpointer so the paused
run can resume:

```python
from langgraph.types import interrupt

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware


class Rejected(Exception):
    """Raised when a reviewer rejects a tool call."""


def require_approval(decision, event):
    # No `decision.duplicate` check: the resumed step calls interrupt() again to read the answer.
    if decision.intervention.kind is InterventionType.HUMAN_REVIEW:
        if interrupt({"reason": decision.intervention.reason}) != "approve":
            raise Rejected(decision.intervention.reason)


engine = BehaviorEngine(
    policies=[PolicyRule("confirm-repeat", "repeated_tool_call", 2, InterventionType.HUMAN_REVIEW)]
)
middleware = BehaviorWeaveMiddleware(engine, on_decision=require_approval)
```

Resume with `agent.invoke(Command(resume="approve"), config)` to run the call; any other
answer raises `Rejected`.

## Pause for an operator when a tool keeps failing

A `pause` decision on a failure streak halts the scope, so later tool calls are refused, and
the hook pauses the run with `interrupt()`. When the operator approves, release the halt from
the application before resuming:

<!-- skip-snippet: needs a provider-backed chat model -->
```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware


def pause_for_operator(decision, event):
    if decision.intervention.kind is InterventionType.PAUSE:
        interrupt({"reason": decision.intervention.reason, "tool": event.tool_name})


engine = BehaviorEngine(
    policies=[PolicyRule("outage", "failure_streak", 3, InterventionType.PAUSE)]
)
middleware = BehaviorWeaveMiddleware(engine, on_decision=pause_for_operator)
agent = create_agent(model, tools, middleware=[middleware], checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "incident-42"}}
agent.invoke({"messages": [{"role": "user", "content": "Restock SKU A-100."}]}, config)

# Later, when the operator approves:
middleware.release("incident-42")
agent.invoke(Command(resume="approved"), config)
```

Resuming runs the failed tool again. If it now succeeds, the success is recorded; if it fails
again, the redelivered outcome repeats the pause without restoring the released halt. Do not
release from inside the hook: it receives the pause decision again only when the outcome
repeats. To keep refusing the scope's tool calls, resume without releasing. For an advisory
escalation that never refuses tool calls, use a kind outside `block_on`, such as `escalate`.

## Stop a LangGraph loop

Report node executions and route on terminal decisions:

```python
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph import LangGraphEventAdapter

adapter = LangGraphEventAdapter()
engine = BehaviorEngine(
    policies=[PolicyRule("loop-guard", "repeated_node_execution", 3, InterventionType.STOP)]
)


class Draft(TypedDict):
    revisions: int
    stopped_by: str | None


def revise(state: Draft, config: RunnableConfig) -> dict[str, object]:
    scope = config["configurable"]["thread_id"]
    decision = engine.process(adapter.node("revise", scope=scope))
    kind = decision.intervention.kind
    return {
        "revisions": state["revisions"] + 1,
        "stopped_by": decision.intervention.policy if kind.is_terminal else None,
    }


builder = StateGraph(Draft)
builder.add_node("revise", revise)
builder.add_edge(START, "revise")
builder.add_conditional_edges("revise", lambda state: END if state["stopped_by"] else "revise")
graph = builder.compile()
final = graph.invoke({"revisions": 0, "stopped_by": None}, {"configurable": {"thread_id": "doc-7"}})
print(final)  # {'revisions': 3, 'stopped_by': 'loop-guard'}
```

## Detect agents handing work back and forth

Report each transfer of control; `oscillation` counts back-and-forth transitions:

```python
from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph import LangGraphEventAdapter

adapter = LangGraphEventAdapter()
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "ping-pong",
            "oscillation",
            2,
            InterventionType.REDIRECT,
            message="Route this case to a supervisor.",
        )
    ]
)
hops = [("triage", "billing"), ("billing", "triage"), ("triage", "billing"), ("billing", "triage")]
kinds = [
    engine.process(adapter.handoff(source, target, scope="case-9")).intervention.kind.value
    for source, target in hops
]
print(kinds)  # ['noop', 'noop', 'noop', 'redirect']
```

Use `adapter.delegation(...)` and `delegation_streak` for repeated delegation to one agent.

## Cap retries in a custom loop

Report each retry; a success resets the streak:

```python
from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import LangChainEventAdapter

adapter = LangChainEventAdapter()
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "retry-cap",
            "retry_streak",
            3,
            InterventionType.STOP,
            message="Stop retrying and report the outage.",
        )
    ]
)
attempts = 0
while True:
    attempts += 1
    # The call failed; ask BehaviorWeave before retrying.
    decision = engine.process(adapter.retry(scope="job-17", tool_name="fetch_invoice"))
    if decision.intervention.kind.is_terminal:
        break
print(attempts, decision.intervention.message)  # 3 Stop retrying and report the outage.
```

## Guard tools inside an MCP server

Process the call inside each handler so every client is guarded:

<!-- skip-snippet: needs the mcp package and starts a server -->
```python
from mcp.server.mcpserver import MCPServer

from behaviorweave import BehaviorEvent
from behaviorweave.integrations.langchain import default_guidance

mcp = MCPServer("operations")


@mcp.tool()
def get_alarm(machine: str) -> str:
    """Return the current alarm for a machine."""
    decision = engine.process(
        BehaviorEvent.tool_call("get_alarm", {"machine": machine}, scope="mcp-session")
    )
    result = f"{machine}: chamber-pressure warning"
    return f"{result}\n{default_guidance(decision)}" if decision.actionable else result
```

A fixed scope aggregates all clients; derive it from a client or session identifier to
isolate them.

## Tune cooldowns and once-only rules

Pass explicit timestamps to reason about cooldowns, which are measured in event time:

```python
from datetime import UTC, datetime, timedelta

from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule, Outcome

engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "outage",
            "failure_streak",
            2,
            InterventionType.ESCALATE,
            cooldown=timedelta(minutes=10),
        )
    ]
)
start = datetime(2026, 1, 1, tzinfo=UTC)
decisions = [
    engine.process(
        BehaviorEvent.outcome_event(
            Outcome.FAILURE, scope="svc", timestamp=start + timedelta(minutes=minute)
        )
    )
    for minute in (0, 1, 2, 15)
]
print([d.intervention.kind.value for d in decisions])  # ['noop', 'escalate', 'noop', 'escalate']
print(decisions[2].suppressed)  # True
```

Use `once_only=True` for an alert that must fire exactly once per pattern history.

## Audit langgraph-xai provenance after a run

Map the run's recorded tool executions and link each decision to its provenance record:

```python
from typing import TypedDict

from langchain.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph_xai import ProvenanceStore, StoreFilter, XAIRuntime
from langgraph_xai.core import ToolExecutionEvent

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter


@tool
def lookup(item: str) -> str:
    """Look up one inventory item."""
    return f"{item}: in stock"


class Order(TypedDict):
    items: list[str]


def check_stock(state: Order) -> dict[str, list[str]]:
    for item in state["items"]:
        lookup.invoke({"item": item})
    return {}


builder = StateGraph(Order)
builder.add_node("check_stock", check_stock)
builder.add_edge(START, "check_stock")
builder.add_edge("check_stock", END)
runtime = XAIRuntime(application_id="shop", tenant_id="acme", graph_id="orders")
graph = LangGraphXAIEventAdapter.instrument_graph(builder.compile(), runtime=runtime)
with runtime.collect_runs() as runs:
    graph.invoke({"items": ["valve", "valve", "valve"]})
(run,) = runs


async def audit() -> list[str]:
    store = runtime.registry.get(ProvenanceStore)
    query = StoreFilter(
        application_id="shop", tenant_id="acme", run_id=run.run_id, item_type=ToolExecutionEvent
    )
    auditor = BehaviorEngine(
        policies=[PolicyRule("busy", "event_frequency", 3, InterventionType.WARNING)]
    )
    adapter = LangGraphXAIEventAdapter()
    return [
        decision.intervention.reason
        async for record in store.query(query)
        if (decision := auditor.process(adapter.event(record, scope="audit"))).actionable
    ]


print(runtime.run_sync(audit()))  # ["'lookup' occurred 3 times"]
runtime.run_sync(runtime.close())
```

## Keep state in a durable store

Implement `BehaviorStateStore`. Only `update` must be atomic; in Redis or PostgreSQL, run it
in a transaction or with optimistic concurrency, committing only the final result:

```python
from threading import Lock

from behaviorweave import BehaviorEngine, BehaviorEvent, BehaviorState, InterventionType, PolicyRule


class JsonStore:
    """Stores each state as JSON, as a database row or cache entry would."""

    def __init__(self) -> None:
        self._rows: dict[str, str] = {}
        self._lock = Lock()

    def get(self, key: str) -> BehaviorState | None:
        row = self._rows.get(key)
        return BehaviorState.from_json(row) if row is not None else None

    def update(self, key, fn):
        with self._lock:  # one transaction per update
            state = fn(self.get(key))
            self._rows[key] = state.to_json()
            return state

    def put(self, key: str, state: BehaviorState) -> None:
        with self._lock:
            self._rows[key] = state.to_json()

    def delete(self, key: str) -> None:
        with self._lock:
            self._rows.pop(key, None)


engine = BehaviorEngine(
    policies=[PolicyRule("repeat-stop", "repeated_tool_call", 2, InterventionType.STOP)],
    state_store=JsonStore(),
)
kinds = [
    engine.process(BehaviorEvent.tool_call("sync", {"id": 1}, scope="s")).intervention.kind.value
    for _ in range(2)
]
print(kinds)  # ['noop', 'stop']
```

## Send every decision to an audit log

```python
import json

from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule

log: list[str] = []


def audit_sink(record) -> None:
    log.append(
        json.dumps(
            {
                "event": record.event.event_type.value,
                "pattern": record.pattern,
                "decision": record.decision.intervention.kind.value,
            }
        )
    )


engine = BehaviorEngine(
    policies=[PolicyRule("repeat-nudge", "repeated_tool_call", 2, InterventionType.NUDGE)],
    audit_sink=audit_sink,
)
for _ in range(2):
    engine.process(BehaviorEvent.tool_call("search", {"q": "x"}, scope="s"))
print(log[-1])  # {"event": "tool_call", "pattern": "repeated_tool_call", "decision": "nudge"}
```
