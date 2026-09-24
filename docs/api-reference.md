# API reference

This page documents the supported public API. It describes only stable application
interfaces; storage keys, synchronization details, and private integration mechanics
are intentionally not part of the contract.

## Core types

### `BehaviorEngine`

```python
BehaviorEngine(*, policies=(), patterns=None, state_store=None)
```

Creates an engine that evaluates normalized events.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `policies` | `Iterable[PolicyRule]` | `()` | Rules to evaluate after a pattern observation. Rules are considered in priority order when more than one matches. |
| `patterns` | `Iterable[Pattern] \| None` | `None` | Pattern detectors to run. `None` selects the built-in pattern set. Provide a collection only when deliberately replacing that set. |
| `state_store` | compatible state store or `None` | `None` | State storage used to maintain pattern history. `None` uses the in-process store. Supply an application-owned compatible store when state must survive process boundaries. |

#### `process`

```python
engine.process(event)
```

Processes one `BehaviorEvent` and returns an `InterventionDecision`. An event that does
not match any configured pattern returns a `noop` decision. Reprocessing the same
event ID is idempotent for a matching pattern.

| Parameter | Type | Description |
| --- | --- | --- |
| `event` | `BehaviorEvent` | The normalized runtime observation to evaluate. |

### `BehaviorEvent`

```python
BehaviorEvent(
    event_type,
    scope,
    timestamp=<current UTC time>,
    event_id=<generated UUID>,
    execution_id=None,
    thread_id=None,
    run_id=None,
    node_name=None,
    tool_name=None,
    agent_name=None,
    target_agent=None,
    outcome=None,
    metadata={},
    provenance_ref=None,
    fingerprint=None,
)
```

An immutable observation from your agent runtime.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `event_type` | `EventType` | required | The kind of observed activity. |
| `scope` | `str` | required | Non-empty isolation boundary for behavioral history, such as a conversation, thread, run, or tenant-scoped session. |
| `timestamp` | timezone-aware `datetime` | current UTC time | When the event occurred. Naive datetimes raise `ValueError`. |
| `event_id` | `str` | generated UUID | Stable unique event identifier used for idempotency. Reuse it only when retrying delivery of the same event. |
| `execution_id` | `str \| None` | `None` | Optional host execution identifier. |
| `thread_id` | `str \| None` | `None` | Optional framework thread identifier. |
| `run_id` | `str \| None` | `None` | Optional framework run identifier. |
| `node_name` | `str \| None` | `None` | Node that executed, for node events. |
| `tool_name` | `str \| None` | `None` | Tool that was called, for tool events. |
| `agent_name` | `str \| None` | `None` | Agent that initiated a delegation or handoff. |
| `target_agent` | `str \| None` | `None` | Agent receiving a delegation or handoff. |
| `outcome` | `Outcome \| None` | `None` | Result classification for outcome and retry events. |
| `metadata` | `Mapping[str, object]` | empty mapping | JSON-compatible application context. Do not place secrets or chain-of-thought in this field. |
| `provenance_ref` | `str \| None` | `None` | Opaque reference to external provenance or explainability data. |
| `fingerprint` | `str \| None` | `None` | Optional application-defined identity used for pattern comparison. |

The constructor raises `ValueError` when `scope` is empty or `timestamp` lacks a
timezone.

#### `BehaviorEvent.tool_call`

```python
BehaviorEvent.tool_call(tool_name, arguments=None, *, scope, event_id=None)
```

Creates a normalized `tool_call` event and derives a deterministic fingerprint from
the tool name and arguments.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `tool_name` | `str` | required | Name of the invoked tool. |
| `arguments` | `Mapping[str, object] \| None` | `None` | Tool arguments. Equivalent mappings produce the same fingerprint. |
| `scope` | `str` | required | Non-empty behavior isolation boundary. |
| `event_id` | `str \| None` | `None` | Optional stable ID for delivery idempotency; a UUID is generated when omitted. |

#### `BehaviorEvent.outcome_event`

```python
BehaviorEvent.outcome_event(outcome, *, scope, event_id=None, metadata=None)
```

Creates a normalized `outcome` event.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `outcome` | `Outcome` | required | `success`, `failure`, or `retry`. |
| `scope` | `str` | required | Non-empty behavior isolation boundary. |
| `event_id` | `str \| None` | `None` | Optional stable ID for delivery idempotency. |
| `metadata` | `Mapping[str, object] \| None` | `None` | Optional context associated with the outcome. |

#### `identity`, `idempotency_key`, `to_dict`, and `to_json`

`identity()` returns the comparison identity used by built-in patterns. Delegations and
handoffs use `agent_name -> target_agent`; other events use `fingerprint`, node name,
tool name, agent name, or event type in that order.

`idempotency_key()` returns the event ID. `to_dict()` returns a JSON-ready mapping, and
`to_json()` returns its stable JSON representation. These methods take no parameters.

### `PolicyRule`

```python
PolicyRule(
    policy_id,
    pattern_id,
    threshold,
    intervention,
    priority=0,
    cooldown=None,
    once_only=False,
    message=None,
    severity="info",
)
```

Defines when an observed pattern produces an intervention.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `policy_id` | `str` | required | Stable policy identifier recorded in resulting decisions. |
| `pattern_id` | `str` | required | ID of the pattern this rule governs, such as `repeated_tool_call`. |
| `threshold` | `int` | required | Minimum observed count required to activate the rule. |
| `intervention` | `InterventionType` | required | Action requested when the threshold is met. |
| `priority` | `int` | `0` | Tie-breaking precedence among matching rules. Higher values win. |
| `cooldown` | `timedelta \| None` | `None` | Period after an intervention during which further matching decisions are suppressed. |
| `once_only` | `bool` | `False` | When `True`, emit this policy at most once for the same stored behavior history. |
| `message` | `str \| None` | `None` | Operator-facing instruction. If omitted, the observed pattern reason is used. |
| `severity` | `str` | `"info"` | Application-defined severity label copied to the intervention. |

### `PolicyEngine`

```python
PolicyEngine(rules=())
```

Evaluates one pattern observation against policy rules.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `rules` | `Iterable[PolicyRule]` | `()` | Rules available for evaluation. |

`evaluate(observation)` accepts a `PatternObservation` and returns an
`InterventionDecision`. It selects the highest-priority eligible rule, respecting
thresholds, cooldowns, and `once_only`; otherwise it returns `noop`.

### `Intervention`, `Explanation`, and `InterventionDecision`

These immutable result objects are returned by `BehaviorEngine.process`.

```python
Intervention(
    kind,
    message=None,
    reason="",
    pattern=None,
    policy=None,
    scope=None,
    severity="info",
    metadata={},
)
```

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `kind` | `InterventionType` | required | Requested host action. |
| `message` | `str \| None` | `None` | Optional concise instruction for an agent or operator. |
| `reason` | `str` | `""` | Deterministic explanation of the decision. |
| `pattern` | `str \| None` | `None` | Pattern that produced the decision. |
| `policy` | `str \| None` | `None` | Policy that produced the decision. |
| `scope` | `str \| None` | `None` | Scope in which the behavior was observed. |
| `severity` | `str` | `"info"` | Application-defined severity label. |
| `metadata` | `Mapping[str, object]` | empty mapping | Additional safe application context. |

```python
Explanation(pattern, count, threshold, policy, reason, provenance_ref=None)
```

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `pattern` | `str` | required | Observed pattern ID. |
| `count` | `int` | required | Count at evaluation time. |
| `threshold` | `int \| None` | required | Policy threshold, or `None` when unavailable. |
| `policy` | `str \| None` | required | Evaluated policy identifier, if any. |
| `reason` | `str` | required | Deterministic explanation of the observation. |
| `provenance_ref` | `str \| None` | `None` | Optional opaque provenance reference. |

```python
InterventionDecision(intervention, explanation=None, suppressed=False)
```

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `intervention` | `Intervention` | required | The requested action, including `noop` when no action is needed. |
| `explanation` | `Explanation \| None` | `None` | Structured reason for the decision. |
| `suppressed` | `bool` | `False` | `True` when an otherwise eligible policy was withheld by cooldown or `once_only`. |

### `AuditRecord`

```python
AuditRecord(event, pattern, state, decision)
```

An immutable safe-to-record decision summary. It intentionally contains no
chain-of-thought.

| Parameter | Type | Description |
| --- | --- | --- |
| `event` | `BehaviorEvent` | Event that was evaluated. |
| `pattern` | `str \| None` | Matched pattern ID, if any. |
| `state` | `BehaviorState \| None` | Public state snapshot associated with the evaluation, if available. |
| `decision` | `InterventionDecision` | Result returned for the event. |

### `PatternObservation`

```python
PatternObservation(pattern_id, scope, fingerprint, state_key, count, crossed, state, reason)
```

Describes one detector result. Applications normally consume the resulting
`InterventionDecision` rather than construct observations directly, but this immutable
type is public for custom pattern and policy integrations.

| Parameter | Type | Description |
| --- | --- | --- |
| `pattern_id` | `str` | Identifier of the pattern that made the observation. |
| `scope` | `str` | Behavior isolation boundary in which it was observed. |
| `fingerprint` | `str` | Event identity compared by the pattern. |
| `state_key` | `str` | Opaque storage reference for the associated state. Pass it through unchanged; do not parse or construct it. |
| `count` | `int` | Pattern count after the event was applied. |
| `crossed` | `bool` | Whether this event advanced the observation rather than repeating a known event. |
| `state` | `BehaviorState` | Immutable snapshot produced by the pattern. |
| `reason` | `str` | Deterministic, human-readable observation summary. |

### `BehaviorState`

```python
BehaviorState(
    pattern_id,
    scope,
    count=0,
    first_seen=None,
    last_seen=None,
    previous_fingerprint=None,
    current_fingerprint=None,
    event_count=0,
    window_start=None,
    window_end=None,
    threshold_state=False,
    cooldown_until=None,
    intervention_history=(),
    seen_event_ids=(),
    metadata={},
    version=0,
)
```

An immutable snapshot of a pattern's history. The engine creates and advances this
value; construct one directly only when implementing a compatible application-owned
state store.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `pattern_id` | `str` | required | Pattern associated with this history. |
| `scope` | `str` | required | Behavior isolation boundary. |
| `count` | `int` | `0` | Current pattern count. |
| `first_seen` | `datetime \| None` | `None` | Timestamp at which the active count began. |
| `last_seen` | `datetime \| None` | `None` | Timestamp of the most recently accepted event. |
| `previous_fingerprint` | `str \| None` | `None` | Identity immediately preceding the current event identity. |
| `current_fingerprint` | `str \| None` | `None` | Identity associated with the current state. |
| `event_count` | `int` | `0` | Number of accepted events represented by this state. |
| `window_start` | `datetime \| None` | `None` | Start of the current observation window. |
| `window_end` | `datetime \| None` | `None` | End of the current observation window. |
| `threshold_state` | `bool` | `False` | Application-visible threshold marker retained in the state snapshot. |
| `cooldown_until` | `datetime \| None` | `None` | Timestamp until which a cooled-down policy remains suppressed. |
| `intervention_history` | `tuple[str, ...]` | `()` | Policy IDs already applied to this history. |
| `seen_event_ids` | `tuple[str, ...]` | `()` | Recent accepted event IDs used for idempotency. |
| `metadata` | `dict[str, object]` | empty mapping | Application-owned state metadata. |
| `version` | `int` | `0` | Monotonically advanced state version. |

`json()` takes no parameters and returns a deterministic JSON representation of the
snapshot.

## Built-in patterns

`built_in_patterns()` takes no parameters and returns the standard pattern collection:

| Pattern ID | Observes |
| --- | --- |
| `repeated_tool_call` | Consecutive identical tool calls. |
| `repeated_node_execution` | Consecutive identical node executions. |
| `failure_streak` | Consecutive failure outcomes. |
| `retry_streak` | Retry activity and retry outcomes. |
| `success_streak` | Consecutive success outcomes. |
| `delegation_streak` | Consecutive identical delegations. |
| `event_frequency` | Total occurrences of an event identity. |

## Enumerations

### `EventType`

`tool_call`, `node_execution`, `agent_handoff`, `delegation`, `outcome`, `retry`, and
`custom`.

### `Outcome`

`success`, `failure`, and `retry`.

### `InterventionType`

`noop`, `nudge`, `warning`, `redirect`, `retry`, `escalate`, `human_review`,
`force_synthesis`, `pause`, `stop`, and `custom`. These are requests to the host
runtime, not direct graph-control operations.

## Framework adapters

Adapters turn framework activity into `BehaviorEvent` values. Create an adapter with
no constructor parameters.

### `LangChainEventAdapter`

```python
from behaviorweave.integrations.langchain import LangChainEventAdapter
```

| Method | Parameters | Returns |
| --- | --- | --- |
| `tool_start(tool_name, *, scope, arguments=None)` | `tool_name`: invoked tool name; `scope`: non-empty behavior boundary; `arguments`: optional tool-argument mapping. | A `tool_call` event. |
| `tool_error(*, scope, error_type)` | `scope`: behavior boundary; `error_type`: stable application/framework error classification. | A failure `outcome` event. |
| `retry(*, scope)` | `scope`: behavior boundary. | A retry event with retry outcome. |

### `LangGraphEventAdapter`

```python
from behaviorweave.integrations.langgraph import LangGraphEventAdapter
```

| Method | Parameters | Returns |
| --- | --- | --- |
| `node(node_name, *, scope, metadata=None)` | `node_name`: executing graph node; `scope`: behavior boundary; `metadata`: optional safe context. | A `node_execution` event. |
| `tool(tool_name, *, scope, arguments=None)` | `tool_name`: invoked tool; `scope`: behavior boundary; `arguments`: optional tool-argument mapping. | A `tool_call` event. |
| `outcome(outcome, *, scope)` | `outcome`: success, failure, or retry; `scope`: behavior boundary. | An `outcome` event. |

### `LangGraphXAIEventAdapter`

```python
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter
```

| Method | Parameters | Returns |
| --- | --- | --- |
| `event(payload, *, scope, provenance_ref=None)` | `payload`: public provenance payload mapping; `scope`: behavior boundary; `provenance_ref`: optional opaque provenance reference. Unknown event types become `custom`. | A normalized `BehaviorEvent`. |
| `instrument_graph(graph, *, application_id="behaviorweave", tenant_id="default", graph_id="graph")` | `graph`: compiled LangGraph graph; `application_id`: logical application identifier; `tenant_id`: provenance tenant identifier; `graph_id`: logical graph identifier. | The graph instrumented through `langgraph-xai`'s public runtime API. |

## Local state store

### `InMemoryBehaviorStateStore`

```python
InMemoryBehaviorStateStore(ttl=None)
```

Provides local, process-scoped state for development, tests, and a single-process
service. The constructor parameter `ttl` is an optional `timedelta`; when set, a state
entry expires after that duration. Use an application-owned compatible store for
distributed or durable execution.

| Method | Parameters | Returns |
| --- | --- | --- |
| `get(key)` | `key`: opaque state reference returned by a pattern observation. | `BehaviorState` or `None` when no current state exists. |
| `put(key, state)` | `key`: opaque state reference; `state`: snapshot to store. | `None`. |
| `update(key, fn)` | `key`: opaque state reference; `fn`: function accepting the current `BehaviorState` or `None` and returning the replacement state. | The resulting `BehaviorState`. |
| `delete(key)` | `key`: opaque state reference to remove. | `None`. |
