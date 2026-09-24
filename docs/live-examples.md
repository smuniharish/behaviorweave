# Live agent examples

BehaviorWeave examples have two explicit modes:

- **Local deterministic tests** validate policy behavior without a provider or a secret.
- **Live examples** use a real OpenAI-compatible model and observe actual LangChain
  tool/delegation calls in the host process.

## Configure the live model

```text
uv sync --extra real-model
$env:EXPLABS_API_KEY = "<your credential>"
```

The credential is intentionally read only from the process environment. Do not commit
a `.env` file or put credentials into an example.

## Real LangChain agent

The essential integration is a real model, a real LangChain agent, and a tool wrapper
that calls BehaviorWeave immediately before returning the actual tool result:

```python
from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule
from langchain.agents import create_agent
from langchain.tools import tool

engine = BehaviorEngine(policies=[
    PolicyRule("repeat-tool", "repeated_tool_call", 2, InterventionType.NUDGE)
])

@tool
def get_alarm(machine: str) -> str:
    """Read the current alarm for a machine."""
    decision = engine.process(BehaviorEvent.tool_call("get_alarm", {"machine": machine}, scope="incident-42"))
    alarm = f"{machine}: chamber-pressure warning; severity=medium."
    if decision.intervention.kind is InterventionType.NUDGE:
        return f"{alarm}\nBehaviorWeave: reuse the existing result."
    return alarm

agent = create_agent(model, [get_alarm])
result = agent.invoke({
    "messages": [{"role": "user", "content": "Call get_alarm for ETCH-3 twice."}]
})
print(result["messages"][-1].content)
```

Run the complete example with `uv run python examples/01_langchain_agent.py`.
The agent is built through `langchain.agents.create_agent`; its `get_alarm` and
`search_incident_history` tools are real LangChain tools. The second call returns this
deterministic tool result to the live agent:

```text
Alarm for ETCH-3: chamber-pressure warning; severity=medium.
BehaviorWeave intervention=nudge; policy=repeat-nudge;
guidance=Reuse the existing tool result; do not call this tool again.
```

The final model wording is intentionally not asserted because it is provider-generated.

## Real MCP tool discovery and execution

```python
async with MCPAdapter(Path("examples/local_alarm_mcp.py")) as adapter:
    mcp_tools = await adapter.list_tools()
    agent = create_agent(model, mcp_tools)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "Inspect ETCH-3."}]})
```

`local_alarm_mcp.py` is an actual MCPServer run over stdio, not a direct Python
function call. `02_langchain_mcp_live.py` connects through LangChain’s public
`MCPAdapter`, discovers the server tools with `list_tools()`, and supplies those tools
to `create_agent`. The server process evaluates BehaviorWeave at the real MCP tool
boundary. Configure a remote HTTP or stdio server in production by replacing the local
server target passed to `MCPAdapter`; do not hard-code server credentials in this repo.

The local MCP integration was executed without a model credential. Its verified second
and third tool responses were:

```text
ETCH-3: chamber-pressure warning; severity=medium; current_status=active.
BehaviorWeave intervention=nudge; guidance=Reuse this MCP result instead of requesting the same alarm again.

ETCH-3: chamber-pressure warning; severity=medium; current_status=active.
BehaviorWeave intervention=force_synthesis; guidance=Stop repeated MCP calls and synthesize the evidence already received.
```

To target a remote MCP server instead of the included stdio server, set
`BEHAVIORWEAVE_MCP_URL` to its `https://.../mcp` endpoint before running the example.
The endpoint must expose tools that are safe to call with the configured model.

## Real LangGraph graph

```python
builder = StateGraph(IncidentState)
builder.add_node("investigate", investigate)
builder.add_edge(START, "investigate")
builder.add_edge("investigate", END)
report = builder.compile().invoke({"request": "Produce an ETCH-3 incident report."})
```

Run the complete example with `uv run python examples/03_langgraph_custom_graph.py`.
The result is a graph state containing `report`, whose live-model wording varies while
the guarded tool evidence and intervention format remain deterministic.

## Real multi-agent delegation

The supervisor is a real LangChain agent and each delegation tool invokes another
real agent. BehaviorWeave evaluates the actual delegation call before a specialist is
invoked:

```python
@tool
def ask_researcher(question: str) -> str:
    decision = engine.process(BehaviorEvent(
        EventType.DELEGATION, scope="incident-42",
        agent_name="supervisor", target_agent="researcher",
    ))
    if decision.intervention.kind is InterventionType.WARNING:
        return "BehaviorWeave: reuse the existing researcher finding."
    return researcher.invoke({"messages": [{"role": "user", "content": question}]})["messages"][-1].content

supervisor = create_agent(model, [ask_researcher, ask_analyst, ask_writer])
result = supervisor.invoke({"messages": [{"role": "user", "content": task}]})
```

```text
uv run python examples/04_langgraph_multi_agent.py
```

The supervisor and each specialist are live LangChain agents. The supervisor’s
delegation tools invoke specialists for researcher, analyst, and writer work.
BehaviorWeave evaluates each delegation boundary and advises the supervisor when a
specialist is invoked repeatedly. On a repeated delegation, the specialist tool returns:

```text
BehaviorWeave=warning: The same specialist was delegated repeatedly; use its existing finding.
```

## Real LangGraph Swarm and Deep Agents

The Swarm example uses `langgraph-swarm`'s public graph and handoff APIs:

```python
alarm_agent = create_agent(
    model, [create_handoff_tool(agent_name="history_agent")], name="alarm_agent"
)
history_agent = create_agent(
    model, [create_handoff_tool(agent_name="alarm_agent")], name="history_agent"
)
swarm = create_swarm(
    [alarm_agent, history_agent], default_active_agent="alarm_agent"
).compile()
result = swarm.invoke({"messages": [{"role": "user", "content": task}]})
```

The Deep Agents subagent example uses its public declarative subagent API:

```python
agent = create_deep_agent(
    model=model,
    tools=[get_alarm],
    subagents=[
        SubAgent(
            name="incident_researcher",
            description="Collect alarm and incident-history evidence for one machine.",
            model=model,
            tools=[get_alarm],
        )
    ],
)
```

```text
uv sync --extra examples --extra real-model
uv run python examples/05_langgraph_swarm.py
uv run python examples/06_deepagents.py
uv run python examples/07_deepagents_subagents.py
```

These execute the actual `langgraph-swarm` and `deepagents` public APIs. The Swarm
example compiles a swarm from two LangChain agents and public handoff tools. The Deep
Agents examples call `create_deep_agent`; the subagent version uses real `SubAgent`
specifications and delegates live work. Both Deep Agent paths use the same guarded
operational tools as the core live agent examples.

## Live policy scenarios

Examples `08_failure_streak.py` through `13_multi_scope.py` use a real LangChain
agent and an actual LangChain tool boundary to demonstrate outcome streaks, retries,
handoff activity, cooldown, escalation, and scope isolation. For example,
`08_failure_streak.py` runs this live agent instruction:

```python
run_live_behavior_scenario(
    scenario="failure-streak",
    event_type=EventType.OUTCOME,
    outcome=Outcome.FAILURE,
    policies=[PolicyRule("failure-escalate", "failure_streak", 3, InterventionType.ESCALATE)],
    prompt="Call record_scenario_action exactly three times with action 'database-timeout'.",
)
```

The third real tool call returns:

```text
Recorded failure-streak action=database-timeout.
BehaviorWeave intervention=escalate; policy=failure-escalate;
guidance=failure_streak observed 3 consecutive times
```

`14_concurrency.py` performs **100 real model-backed LangChain agent runs by default**,
each calling a real guarded tool. It shares one guard. When each worker completes its
required tool call, its final summary has this form:

```text
Completed 100 real model-backed LangChain agent runs; observed tool-repeat count=100.
```

It incurs 100 provider requests; set `BEHAVIORWEAVE_CONCURRENCY_CALLS` only when you
intentionally need a different load.

## Flagship: LangGraph plus langgraph-xai

```text
uv run python examples/15_complete_agent_guard.py
```

This example compiles an explicit LangGraph graph, instruments it with the public
`XAIRuntime.instrument` path through `LangGraphXAIEventAdapter`, and invokes the
live BehaviorWeave-guarded agent in the graph node.

## Validation boundary

The live examples are intentionally excluded from automated CI because they make paid,
nondeterministic external calls. Their imports, construction paths, local tools, and
deterministic policy behavior are tested locally; actual provider execution requires a
credential that is never stored in this repository.
