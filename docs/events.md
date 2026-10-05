# Events

A [`BehaviorEvent`][behaviorweave.BehaviorEvent] is an immutable, normalized observation of
something your agent did. Every pattern, policy, and decision in BehaviorWeave works on
events, so a single model covers tool calls, graph nodes, outcomes, retries, handoffs, and
delegations from any framework.

## Event types

| `EventType` | Reported when | Typical fields |
| --- | --- | --- |
| `tool_call` | A tool is about to run. | `tool_name`, `fingerprint` |
| `node_execution` | A graph node runs. | `node_name` |
| `agent_handoff` | Control passes to another agent. | `agent_name`, `target_agent` |
| `delegation` | An agent delegates work to another agent. | `agent_name`, `target_agent` |
| `outcome` | A unit of work finishes. | `outcome`, optionally `tool_name` or `node_name` |
| `retry` | A unit of work is retried. | optionally `tool_name` |
| `custom` | Anything else your application wants to track. | your choice |

Build events with the constructor or with the factories:

```python
from datetime import UTC, datetime

from behaviorweave import BehaviorEvent, EventType, Outcome

call = BehaviorEvent.tool_call(
    "search", {"query": "pressure drift"}, scope="thread-1"
)
failed = BehaviorEvent.outcome_event(
    Outcome.FAILURE, scope="thread-1", tool_name="search"
)
handoff = BehaviorEvent(
    EventType.AGENT_HANDOFF,
    scope="thread-1",
    agent_name="triage",
    target_agent="billing",
    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
)
```

Construction validates every event: an empty `scope` or `event_id`, a naive timestamp, or an
unknown event type raises [`EventValidationError`][behaviorweave.EventValidationError].

## Scope

`scope` is the isolation boundary for behavioral history. Events in different scopes never
influence each other, so choose the unit your policies should reason about: a conversation,
a LangGraph thread, a run, or a tenant-qualified session such as `"tenant-7:thread-42"`.

## Identity and fingerprints

Patterns compare events by [`identity()`][behaviorweave.BehaviorEvent.identity]:

1. an explicit `fingerprint`, when you set one;
2. `agent_name->target_agent` for handoffs and delegations;
3. otherwise the node, tool, or agent name; outcome events append their outcome.

```python
print(handoff.identity())  # triage->billing
print(failed.identity())  # search:failure
```

`BehaviorEvent.tool_call` derives the fingerprint from the tool name and a SHA-256 digest of
the canonical arguments. Equivalent arguments always match, regardless of key order, and the
fingerprint never contains raw argument values:

```python
first = BehaviorEvent.tool_call("search", {"q": "x", "page": 1}, scope="s")
second = BehaviorEvent.tool_call("search", {"page": 1, "q": "x"}, scope="s")
assert first.fingerprint == second.fingerprint
assert "page" not in first.fingerprint
```

Arguments of any type can be fingerprinted: sets, tuples, dates, Pydantic models, and
arbitrary objects are canonicalized deterministically.

## Idempotent delivery

Every event has an `event_id` (a random UUID by default). Redelivering an event that was
already processed, for example after a retry, a crash, or a resumed graph step, changes no
state. If the original decision was actionable, it is returned again, marked `duplicate`;
otherwise the result is a `noop` marked `duplicate`. A host that lost a decision can
therefore safely process the same event again and apply the answer; check
`decision.duplicate` before repeating side effects such as paging an operator. Events that
no policy's pattern observes leave no state behind, so their redelivery returns an unmarked
`noop`.

```python
from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionType,
    PolicyRule,
)

engine = BehaviorEngine(
    policies=[
        PolicyRule("stop", "repeated_tool_call", 1, InterventionType.STOP)
    ]
)
event = BehaviorEvent.tool_call("wipe", {"db": "prod"}, scope="ops")
first, again = engine.process(event), engine.process(event)
print(first.intervention.kind.value, again.intervention.kind.value)  # stop stop
print(first.duplicate, again.duplicate)  # False True
```

Reuse an ID only when redelivering the same observation.

## Serialization

`to_dict()` and `to_json()` produce stable, JSON-safe representations. Metadata that is not
JSON-native is canonicalized rather than raising:

```python
print(call.to_dict()["event_type"])  # tool_call
```

!!! warning "Keep secrets out of events"
    Event metadata is application context, not a vault. Never put credentials, tokens, or
    private model reasoning in `metadata`. Tool arguments are recorded in
    `metadata["arguments"]`; redact sensitive arguments before reporting the event.
