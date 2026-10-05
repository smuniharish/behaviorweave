# BehaviorWeave troubleshooting

Find the symptom, check the causes in order, and apply the fix. When a decision looks wrong,
inspect it first: `decision.intervention.reason`, `decision.explanation`, `decision.suppressed`,
and `decision.duplicate` say what the engine saw and why it decided.

## An intervention never fires

| Cause | Check | Fix |
| --- | --- | --- |
| The pattern never sees the event. | `failure_streak` needs outcome events; `repeated_node_execution` needs `node_execution` events; `oscillation` needs handoffs or delegations. | Report the right events: enable `track_outcomes`, or use the matching adapter method. |
| The identities differ. | `repeated_tool_call` and `event_frequency` compare the tool name and arguments; `{"page": 1}` and `{"page": 2}` are different calls. | To count calls with different arguments together, build the events yourself with an explicit `fingerprint`, such as the tool name, or implement a custom pattern. |
| The scopes differ. | Every event of one conversation must carry the same `scope` (the middleware uses the `thread_id`). | Pass a stable `thread_id`, or `scope=` to the middleware. |
| The count is reset. | Streaks reset on a contrary outcome; consecutive patterns restart when another identity arrives. | Use `event_frequency` for a total budget. |
| The rule is withheld. | `decision.suppressed` is `True` and the reason names the cooldown or once-only setting. | Shorten or remove the cooldown, or drop `once_only`. |
| Another rule wins. | Within one pattern, the applicable rule with the highest priority and threshold is chosen; if it is withheld, nothing fires in its place. | Adjust `priority` or thresholds. |

A policy that references a pattern the engine does not provide raises
`PolicyConfigurationError` at construction, listing the available pattern IDs.

## An intervention fires on every event

- The threshold is 1, or the pattern is `event_frequency`, which never resets. Raise the
  threshold, add a `cooldown`, or set `once_only=True`.
- Several unrelated conversations share one scope. Scope by conversation, thread, or
  tenant-qualified session.

## `BehaviorWeaveMiddleware needs a scope`

The middleware takes the scope from `config["configurable"]["thread_id"]`. Invoke the agent
with `config={"configurable": {"thread_id": ...}}`, or construct the middleware with
`scope="..."` or a callable that derives the scope from the request.

## Every tool call is refused

The scope is halted: an outcome decision whose kind is in `block_on` (by default `stop` or
`pause`) arrived after the tool already ran, so later calls in that scope are refused. Handle
the cause, then call `middleware.release(scope)`. Halts are kept in memory by the middleware
instance. A replayed step whose own outcome caused the halt is not refused.

If the scope stays halted after an operator resumed a paused run, the halt was probably
released from inside `on_decision`. The resumed tool runs again, and when it now succeeds, the
hook does not receive the pause decision again. Release the halt from the application before
resuming instead.

## Guidance does not reach the model

- Only actionable decisions add guidance; check that the decision is not `noop`.
- Guidance is appended to `ToolMessage` results. A tool that returns a `Command` is passed
  through unchanged.
- A custom `formatter` must return the text to append.

## A redelivered event acts twice, or not at all

- A redelivered event (the same `event_id`) that a policy's pattern recorded changes no state.
  An actionable original decision is repeated with `duplicate=True`; any other, including a
  suppressed one, comes back as a plain `noop` marked `duplicate`. Events that no policy's
  pattern observes leave no trace, so they return an unmarked `noop` again.
- Check `decision.duplicate` before repeating external side effects such as paging an
  operator, but do not skip `interrupt()` for duplicates: a resumed step runs the hook again,
  and `interrupt()` returns the reviewer's answer only when it is called.
- Distinct observations need distinct event IDs. Reusing an ID for a new observation makes
  the engine treat it as a redelivery.
- The middleware derives event IDs from the tool-call ID, so replayed and resumed graph steps
  are recognized as redeliveries. The tool itself runs again, and if its outcome changes, the
  new outcome is recorded.

## langgraph-xai events

- A cancelled or interrupted node or tool, or a cancelled run, carries no outcome, so it
  neither extends nor resets a streak.
- langgraph-xai records tool executions without their arguments, so a mapped tool call's
  identity is its tool name.
- `instrument_graph` creates a runtime when none is passed; pass your own `XAIRuntime` to
  query its provenance store and to `close()` it when you are done.

## Memory keeps growing

`InMemoryBehaviorStateStore` keeps one state per scope and pattern history. Call
`store.clear(scope)` when a conversation ends, or pass `ttl=timedelta(...)` so idle histories
expire. For several processes or restarts, implement `BehaviorStateStore` on a shared,
durable backend.

## Type or validation errors

- `EventValidationError`: an empty scope or event ID, a naive `timestamp`, or an unknown
  event type or outcome.
- `PolicyConfigurationError`: an invalid rule, a duplicate policy or pattern ID, or an
  unknown pattern reference.
- `StateStoreError`: a store returned something other than a `BehaviorState`, a non-positive
  `ttl`, or unreadable serialized state.

All three subclass `BehaviorWeaveError` and `ValueError`.
