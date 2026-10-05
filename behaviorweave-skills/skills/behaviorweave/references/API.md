# BehaviorWeave API reference

Everything below is public and typed. Import core classes from the package root and each
integration from its own module. The full generated reference is at
<https://behaviorweave.readthedocs.io/en/latest/api-reference/>.

```python
from behaviorweave import (
    AuditRecord,
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    BehaviorStateStore,
    BehaviorWeaveError,
    ConsecutivePattern,
    EventType,
    EventValidationError,
    Explanation,
    FrequencyPattern,
    InMemoryBehaviorStateStore,
    Intervention,
    InterventionDecision,
    InterventionType,
    OscillationPattern,
    Outcome,
    Pattern,
    PatternObservation,
    PolicyConfigurationError,
    PolicyEngine,
    PolicyRule,
    StateStoreError,
    StreakPattern,
    built_in_patterns,
)
from behaviorweave.integrations.langchain import (
    BehaviorWeaveMiddleware,
    LangChainEventAdapter,
    default_guidance,
)
from behaviorweave.integrations.langgraph import LangGraphEventAdapter
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter
```

## Engine

`BehaviorEngine(*, policies=(), patterns=None, state_store=None, audit_sink=None)`

- `policies`: `PolicyRule` instances. Policy IDs must be unique, and every referenced
  pattern must exist.
- `patterns`: `None` selects `built_in_patterns()`; an empty collection provides none. Pass
  `[*built_in_patterns(), MyPattern()]` to add your own.
- `state_store`: any `BehaviorStateStore`; defaults to a new `InMemoryBehaviorStateStore()`.
- `audit_sink`: a callable receiving one `AuditRecord` per processed event, after the
  decision is recorded.
- `process(event) -> InterventionDecision`: thread-safe; evaluates only patterns referenced
  by a policy and returns the strongest decision (actionable over `noop`, then rule
  `priority`, terminal kinds, pattern count, and pattern declaration order).
- `rules`: the configured `PolicyRule` tuple. `store`: the state store.

Raises `PolicyConfigurationError` for duplicate pattern IDs, non-pattern items, or policies
that reference an unknown pattern.

## Policies

`PolicyRule(policy_id, pattern_id, threshold, intervention, priority=0, cooldown=None, once_only=False, message=None, severity="info")`

| Field | Meaning |
| --- | --- |
| `threshold` | Minimum pattern count (an integer, at least 1) at which the rule applies. |
| `intervention` | An `InterventionType` or its string value; never `noop`. |
| `priority` | Higher wins among the applicable rules of one pattern. |
| `cooldown` | Positive `timedelta`; suppresses this policy alone for that long after it fires, in event time. |
| `once_only` | Fire at most once per pattern history. |
| `message` | Instruction returned as `intervention.message` (guidance text for the agent). |
| `severity` | Free-form label copied to the intervention. |

Within one pattern, the applicable rule with the highest `priority` wins, then the higher
`threshold`, then terminal kinds, then declaration order. If that rule is withheld by its
cooldown or `once_only`, the decision is a `noop` with `suppressed=True`; a lower rule does not
fire in its place. Cooldowns and once-only history are kept per scope for consecutive,
streak, and oscillation patterns, and per scope and identity for `event_frequency`.

## Interventions and decisions

`InterventionType`: `noop`, `nudge`, `warning`, `redirect`, `retry`, `escalate`,
`human_review`, `force_synthesis`, `pause`, `stop`, `custom`. `kind.is_terminal` is `True`
for `stop` and `pause`.

`InterventionDecision` fields:

| Field | Meaning |
| --- | --- |
| `intervention` | `Intervention(kind, message, reason, pattern, policy, scope, severity, metadata)`; `reason` describes the observed behavior, `message` is the policy's instruction. |
| `explanation` | `Explanation(pattern, count, threshold, policy, reason, provenance_ref)` for actionable and suppressed decisions, otherwise `None`. |
| `suppressed` | A rule applied but was withheld by its cooldown or once-only setting. |
| `duplicate` | The event was a redelivery of an event that a policy's pattern recorded: no state changed. An actionable original decision is repeated; any other, including a suppressed one, comes back as a plain `noop`. Events that no policy's pattern observes leave no trace and return an unmarked `noop` again. |
| `actionable` | Property: `True` unless the kind is `noop`. |

`AuditRecord(event, pattern, state, decision)` is what `audit_sink` receives.

## Events

`BehaviorEvent(event_type, scope, timestamp=now, event_id=uuid4, execution_id=None, thread_id=None, run_id=None, node_name=None, tool_name=None, agent_name=None, target_agent=None, outcome=None, metadata={}, provenance_ref=None, fingerprint=None)`

- `EventType`: `tool_call`, `node_execution`, `agent_handoff`, `delegation`, `outcome`,
  `retry`, `custom`. `Outcome`: `success`, `failure`, `retry`.
- `scope` must be non-empty and `timestamp` timezone-aware; invalid fields raise
  `EventValidationError`. Events are immutable; `metadata` is read-only.
- `BehaviorEvent.tool_call(tool_name, arguments=None, *, scope, event_id=None, timestamp=None, thread_id=None, run_id=None, metadata=None, provenance_ref=None)`
  fingerprints the tool name with a SHA-256 digest of the canonical arguments
  (`tool_name#<digest>`) and records the arguments as `metadata["arguments"]`.
- `BehaviorEvent.outcome_event(outcome, *, scope, event_id=None, timestamp=None, tool_name=None, node_name=None, thread_id=None, run_id=None, metadata=None, provenance_ref=None)`.
- `identity()`: what patterns compare. An explicit `fingerprint` wins; handoffs and
  delegations use `agent->target`; otherwise the node, tool, or agent name, with the outcome
  appended for outcome events.
- `to_dict()` and `to_json()` produce stable, JSON-safe representations.

## Patterns

| Built-in ID | Class | Counts |
| --- | --- | --- |
| `repeated_tool_call` | `ConsecutivePattern` | Consecutive calls with the same tool and arguments. |
| `repeated_node_execution` | `ConsecutivePattern` | Consecutive executions of the same node. |
| `failure_streak` | `StreakPattern` | Consecutive failures; a success resets it. |
| `retry_streak` | `StreakPattern` | Consecutive retries; a success resets it. |
| `success_streak` | `StreakPattern` | Consecutive successes; a failure or retry resets it. |
| `delegation_streak` | `ConsecutivePattern` | Consecutive delegations to the same agent. |
| `oscillation` | `OscillationPattern` | Back-and-forth handoffs or delegations between two agents. |
| `event_frequency` | `FrequencyPattern` | Total occurrences of each event identity, per event type; never resets. |

Configure your own instances with your own IDs:
`ConsecutivePattern(pattern_id, event_types)`,
`StreakPattern(pattern_id, counts, resets=frozenset())`,
`OscillationPattern(pattern_id, event_types)`, and `FrequencyPattern(pattern_id, event_types)`.
A custom detector implements the `Pattern` protocol: a `pattern_id`, `matches(event)`, and
`observe(event, store) -> PatternObservation`, advancing state only through
`store.update(key, fn)`.

## State

- `InMemoryBehaviorStateStore(ttl=None, *, clock=None)`: thread-safe and process-local.
  `ttl` refreshes on every write; `clear(scope=None)` and `purge_expired()` return the number
  of removed states.
- `BehaviorStateStore` protocol for durable backends: `get(key)`, `update(key, fn)` (atomic;
  the only method the engine needs), `put(key, state)`, and `delete(key)`.
- `BehaviorState` is an immutable snapshot with `to_dict`, `to_json`, `from_dict`, and
  `from_json` for storage.

## LangChain

`BehaviorWeaveMiddleware(engine, *, scope=None, block_on=(STOP, PAUSE), track_outcomes=True, on_decision=None, formatter=None, name=None)`

- `scope`: a string, or a callable `(ToolCallRequest) -> str`; by default the LangGraph
  `thread_id` from the run configuration.
- `block_on`: kinds that refuse a tool call before it runs, returning an error `ToolMessage`.
- `track_outcomes`: record a `success` or `failure` outcome per tool result. A blocking
  outcome decision halts the scope until `release(scope) -> bool`, which the application
  calls, for example before resuming a run that the hook paused.
- `on_decision(decision, event)`: called for every decision; raise or call `interrupt()` in
  it to stop or pause the run. Call `interrupt()` for duplicates too, so a resumed step reads
  the answer. A replayed step runs its tool again, and a changed outcome is recorded.
- `formatter(decision) -> str`: guidance text; defaults to `default_guidance`, which renders
  `[BehaviorWeave:<kind>] <message or reason>`.
- `name`: set it when one agent uses several instances.

`LangChainEventAdapter` builds events for custom tool lifecycles: `tool_start(tool_name, *,
scope, arguments=None, event_id=None)`, `tool_end(*, scope, tool_name=None, event_id=None)`,
`tool_error(*, scope, error_type, tool_name=None, event_id=None)`, and `retry(*, scope,
tool_name=None, event_id=None)`.

## LangGraph

`LangGraphEventAdapter` methods return events and never route: `node(node_name, *, scope,
metadata=None, event_id=None)`, `tool(tool_name, *, scope, arguments=None, event_id=None)`,
`outcome(outcome, *, scope, node_name=None, event_id=None)`, `handoff(source_agent,
target_agent, *, scope, event_id=None)`, and `delegation(source_agent, target_agent, *,
scope, event_id=None)`.

## langgraph-xai

- `LangGraphXAIEventAdapter().event(payload, *, scope, provenance_ref=None)` maps a canonical
  langgraph-xai 1.x event (the model or its `model_dump()`): `node.execution` becomes
  `node_execution` named by its node ID, `tool.execution` becomes `tool_call`, and
  `execution.completed` and `execution.failed` become `success` and `failure` outcomes.
  Cancelled or interrupted work and cancelled runs carry no outcome. The canonical `id`
  becomes the `event_id` and the default `provenance_ref`.
- `LangGraphXAIEventAdapter.instrument_graph(graph, *, runtime=None, application_id="behaviorweave", tenant_id="default", graph_id="graph")`
  returns `runtime.instrument(graph)`, creating a runtime when none is given.

## Errors

`BehaviorWeaveError` is the base class. `EventValidationError`,
`PolicyConfigurationError`, and `StateStoreError` also subclass `ValueError`.
