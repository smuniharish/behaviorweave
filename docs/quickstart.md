# Quickstart

BehaviorWeave observes runtime events, evaluates your policies, and returns an intervention
decision. It never takes control of your agent or graph: your application decides how to
apply each decision.

## Install

BehaviorWeave supports Python 3.12, 3.13, and 3.14.

=== "uv"

    ```bash
    uv add behaviorweave
    ```

=== "pip"

    ```bash
    pip install behaviorweave
    ```

The install includes LangChain, LangGraph, and `langgraph-xai`, which the integrations use.

## 1. Define policies

A policy joins a [pattern](patterns.md) to an intervention. These two rules nudge an agent
on its second identical tool call and stop it on the third.

```python
from behaviorweave import BehaviorEngine, InterventionType, PolicyRule

engine = BehaviorEngine(
    policies=[
        PolicyRule(
            policy_id="repeat-nudge",
            pattern_id="repeated_tool_call",
            threshold=2,
            intervention=InterventionType.NUDGE,
            message="Reuse the result you already have.",
        ),
        PolicyRule(
            policy_id="repeat-stop",
            pattern_id="repeated_tool_call",
            threshold=3,
            intervention=InterventionType.STOP,
            message="Identical call blocked. Answer with what you have.",
        ),
    ]
)
```

The engine ships with the [built-in patterns](patterns.md#built-in-patterns); policies only
name the pattern they govern. A typo in a pattern ID raises `PolicyConfigurationError`
immediately instead of silently never firing.

## 2. Process events where behavior is observable

Report an event at the runtime boundary, for example right before a tool runs. The `scope`
isolates behavioral history: use a conversation, thread, or run identifier.

```python
from behaviorweave import BehaviorEvent

decisions = [
    engine.process(
        BehaviorEvent.tool_call(
            "lookup_customer", {"customer_id": "42"}, scope="conversation-42"
        )
    )
    for _ in range(3)
]

print(
    [d.intervention.kind.value for d in decisions]
)  # ['noop', 'nudge', 'stop']
print(decisions[1].intervention.message)  # Reuse the result you already have.
```

Every decision carries an explanation:

```python
explanation = decisions[2].explanation
assert explanation is not None
print(
    explanation.policy, explanation.count, explanation.threshold
)  # repeat-stop 3 3
print(explanation.reason)  # 'lookup_customer' occurred 3 consecutive times
```

## 3. Apply the decision

BehaviorWeave returns data. Map each intervention to the behavior your application needs:

```python
def apply(decision):
    kind = decision.intervention.kind
    if kind.is_terminal:  # stop or pause
        return f"halt: {decision.intervention.message}"
    if kind is InterventionType.HUMAN_REVIEW:
        return "page an operator"
    if decision.actionable:
        return f"tell the agent: {decision.intervention.message}"
    return "continue"


actions = [apply(d) for d in decisions]
print(actions[0])  # continue
print(actions[1])  # tell the agent: Reuse the result you already have.
print(actions[2])  # halt: Identical call blocked. Answer with what you have.
```

## 4. Guard a LangChain agent in one line

For LangChain v1 agents, `BehaviorWeaveMiddleware` does all of the above for every tool
call: it reports the call, appends guidance to the tool result, blocks the call on `stop`
or `pause`, and records success and failure outcomes.

<!-- skip-snippet: requires a provider-backed chat model -->
```python
from langchain.agents import create_agent

from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware

agent = create_agent(
    "openai:gpt-4.1-mini",
    tools=[lookup_customer],
    middleware=[BehaviorWeaveMiddleware(engine)],
)
agent.invoke(
    {"messages": [{"role": "user", "content": "Look up customer 42."}]},
    config={"configurable": {"thread_id": "conversation-42"}},
)
```

The middleware scopes history by the LangGraph `thread_id`, so each conversation is
governed independently.

## Next steps

- Learn how [patterns](patterns.md) count behavior and how [policies](policies.md) choose
  a decision.
- Wire BehaviorWeave into [LangChain](integrations/langchain.md),
  [LangGraph](integrations/langgraph.md), or an [MCP server](integrations/mcp.md).
- Run the [live examples](examples.md) against your own model endpoint.
