# Get started

BehaviorWeave observes meaningful runtime events, evaluates your policies, and returns
an intervention decision. It does not take control of a LangChain agent or LangGraph
graph: your application decides how to apply each decision.

## 1. Install

BehaviorWeave supports Python 3.12 only and uses `uv` for dependency management.

```bash
uv add behaviorweave
```

For a checkout of this repository:

```bash
uv sync
```

The base installation includes LangChain, LangGraph, and `langgraph-xai`. Optional
packages are only needed for the corresponding live examples:

```bash
uv sync --extra real-model  # Provider-backed LangChain examples
uv sync --extra mcp         # Model Context Protocol examples
uv sync --extra examples    # LangGraph Swarm and Deep Agents examples
```

## 2. Define one policy

A policy joins an observable pattern to an intervention. This policy asks the runtime
to nudge an agent after it calls the same tool with the same arguments three times in
succession.

```python
from behaviorweave import BehaviorEngine, InterventionType, PolicyRule

engine = BehaviorEngine(
    policies=[
        PolicyRule(
            policy_id="repeat-lookup-nudge",
            pattern_id="repeated_tool_call",
            threshold=3,
            intervention=InterventionType.NUDGE,
            message="Reuse the lookup result already returned for this request.",
        )
    ]
)
```

`BehaviorEngine` includes the built-in patterns by default. You therefore only need to
name the pattern that the policy should govern.

## 3. Process events at the runtime boundary

Emit an event where the behavior is observable—for example, immediately before a tool
is invoked. Use a stable, application-chosen `scope` such as a LangGraph thread ID,
LangChain run ID, or tenant-and-conversation identifier.

```python
from behaviorweave import BehaviorEvent

for _ in range(3):
    decision = engine.process(
        BehaviorEvent.tool_call(
            "lookup_customer",
            {"customer_id": "42"},
            scope="conversation:42",
        )
    )

print(decision.intervention.kind)
print(decision.intervention.message)
```

Output:

```text
nudge
Reuse the lookup result already returned for this request.
```

The first two events return `noop`; the third crosses the policy threshold and returns
the configured `nudge`.

## 4. Apply the decision

BehaviorWeave returns data and never silently changes graph flow. Map an intervention
to the behavior appropriate for your application:

```python
from behaviorweave import InterventionType

if decision.intervention.kind is InterventionType.NUDGE:
    tool_context["behaviorweave_notice"] = decision.intervention.message
elif decision.intervention.kind is InterventionType.HUMAN_REVIEW:
    request_human_review(decision.intervention.reason)
elif decision.intervention.kind is InterventionType.STOP:
    raise RuntimeError(decision.intervention.reason)
```

## 5. Connect a framework adapter

Adapters normalize framework activity into the same event model. They do not monkey
patch framework internals and do not execute policies themselves.

```python
from behaviorweave import BehaviorEngine
from behaviorweave.integrations.langchain import LangChainEventAdapter

engine = BehaviorEngine(policies=[...])
adapter = LangChainEventAdapter()

def before_tool(tool_name: str, arguments: dict[str, object], run_id: str) -> None:
    event = adapter.tool_start(
        tool_name,
        arguments=arguments,
        scope=f"run:{run_id}",
    )
    decision = engine.process(event)
    # Attach, route, or enforce `decision` in the host runtime.
```

See [API reference](api-reference.md) for every public parameter and
[Live examples](live-examples.md) for complete LangChain, LangGraph, MCP, Swarm, and
Deep Agents integrations.

## Run live-provider examples safely

The repository never stores provider credentials. Install the opt-in model integration
and export the key through your local environment:

```text
uv sync --extra real-model
$env:EXPLABS_API_KEY = "<your-key>"
uv run python examples/01_langchain_agent.py
```

Use a local `.env` only with a dotenv loader or shell integration that you control;
never commit it. The live agent calls actual local operational tools through LangChain.
`BehaviorWeave` observes each tool invocation in real time and injects an intervention
into the tool response when a repeated call crosses a policy threshold.

For a real LangGraph run use `examples/03_langgraph_custom_graph.py`; for a real
supervisor/subagent execution use `examples/04_langgraph_multi_agent.py`; and for the
LangGraph plus `langgraph-xai` flagship run use `examples/15_complete_agent_guard.py`.
All four require `EXPLABS_API_KEY`. They are intentionally opt-in and excluded from CI.

The deterministic examples are intentionally flat files, for example:

```text
examples/04_langgraph_multi_agent.py
examples/14_concurrency.py
```
