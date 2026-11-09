# Testing policies

BehaviorWeave is deterministic, so policies are straightforward to test: build events
with fixed timestamps, process them, and assert on the decisions. No model or network is
needed.

## Unit-test a policy set

Give events explicit timestamps whenever cooldowns are involved; cooldowns are measured in
event time, not wall-clock time.

```python
from datetime import UTC, datetime, timedelta

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionType,
    PolicyRule,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


async def test_nudge_cools_down_but_stop_still_fires() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "nudge",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                cooldown=timedelta(minutes=1),
            ),
            PolicyRule("stop", "repeated_tool_call", 4, InterventionType.STOP),
        ]
    )
    kinds = [
        (
            await engine.process(
                BehaviorEvent.tool_call("sync", scope="s", timestamp=at(i))
            )
        ).intervention.kind.value
        for i in range(4)
    ]
    assert kinds == ["noop", "nudge", "noop", "stop"]


await test_nudge_cools_down_but_stop_still_fires()
```

## Test an agent without a provider

To test middleware wiring end to end, drive `create_agent` with a scripted fake chat model
that emits predetermined tool calls:

```python
from langchain.agents import create_agent
from langchain.messages import AIMessage, ToolMessage
from langchain.tools import tool
from langchain_core.language_models.fake_chat_models import (
    GenericFakeChatModel,
)

from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def call(call_id: str) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": "sync", "args": {}, "id": call_id}]
    )


@tool
async def sync() -> str:
    """Synchronize inventory."""
    return "synced"


engine = BehaviorEngine(
    policies=[
        PolicyRule("stop", "repeated_tool_call", 2, InterventionType.STOP)
    ]
)
model = ScriptedModel(
    messages=iter([call("a"), call("b"), AIMessage(content="done")])
)
agent = create_agent(
    model, [sync], middleware=[BehaviorWeaveMiddleware(engine)]
)
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "sync twice"}]},
    config={"configurable": {"thread_id": "test"}},
)
statuses = [m.status for m in result["messages"] if isinstance(m, ToolMessage)]
assert statuses == ["success", "error"]
```

## Property-based testing

BehaviorWeave's own suite uses [Hypothesis](https://hypothesis.readthedocs.io/) to check its
semantics against simple reference models, including stateful tests that drive the engine
with random tool calls, outcomes, handoffs, redeliveries, and clock jumps, the state store
with random writes and expiry, and the middleware with random halts, releases, and replays.
The same approach works for your policies: generate event sequences and assert invariants
such as "a once-only policy fires at most once" or "`stop` is returned whenever the streak
reaches its threshold".

## A ready-made template

The [Agent Skill](../../agent-skills/index.md) includes `assets/test_behavior_policy.py`, a pytest
template that checks an escalation ladder, argument and scope isolation, redelivery, and
cooldowns. Copy it into your test suite and replace its engine factory with your own.

## Extension contracts

Subclass `BehaviorStateStoreContract` and implement `async make_store()` to return a fresh,
ready-to-use store. The inherited tests check detached snapshots, atomic concurrent updates,
round-trips, invalid values, and lifecycle. The test base closes each store.

```python
from behaviorweave import InMemoryBehaviorStateStore
from behaviorweave.testing import BehaviorStateStoreContract


class TestApplicationStore(BehaviorStateStoreContract):
    async def make_store(self):
        return InMemoryBehaviorStateStore()


TestApplicationStore().test_concurrent_updates_of_one_key_are_serialized()
```

For a custom pattern, subclass `PatternContract`, implementing `make_pattern()` and
`make_event(scope, index)`. Its generated events must be accepted by the pattern.
These are ABCs with no pytest dependency. Override `run_scenario` when the backend requires
a specific event loop.
