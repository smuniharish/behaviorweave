---
name: behaviorweave
description: Integrate, configure, test, and debug BehaviorWeave, the deterministic behavioral policy layer for LangChain and LangGraph agents. Use when an agent repeats the same tool call, loops on a graph node, keeps failing or retrying, delegates in circles, or hands work back and forth between agents, and the fix should be an explicit, explainable intervention (nudge, warning, escalation, human review, pause, or stop) rather than a prompt instruction. Also use to add BehaviorWeaveMiddleware to a create_agent or Deep Agents agent, guard MCP tools, audit langgraph-xai provenance, tune thresholds, cooldowns, and once-only rules, or find out why an intervention never fires. Do not use for generic monitoring, model-based classification of behavior, or building an agent framework.
license: Apache-2.0
compatibility: Python 3.12 or newer with LangChain 1.x and LangGraph 1.x. Installs behaviorweave 1.x from PyPI. scripts/verify_setup.py runs offline in the project's Python environment.
metadata:
  version: "1.0.0"
  documentation: "https://behaviorweave.readthedocs.io"
---

# BehaviorWeave

`behaviorweave` turns observable agent activity (tool calls, node executions, outcomes,
retries, handoffs, and delegations) into events, detects behavioral patterns such as loops,
streaks, and oscillation, evaluates explicit policies, and returns one typed intervention
decision per event. It never executes anything itself: the application, or the optional
LangChain middleware, applies each decision.

Use this skill to add the existing package to an application. It is not an agent framework,
a monitoring backend, or a model-based behavior classifier.

## Before you change anything

1. From the project's Python environment, run the setup check in this skill's directory:

   ```bash
   python scripts/verify_setup.py
   ```

   It checks Python and package versions and runs a guarded agent offline. Fix every `FAIL`
   line first.
2. Find the agents, tool-call sites, graph nodes, and multi-agent boundaries to guard, any
   existing `BehaviorEngine`, and the identifier that should scope behavior (usually the
   LangGraph `thread_id`).
3. Pick the matching recipe in [references/RECIPES.md](references/RECIPES.md). Look up exact
   signatures in [references/API.md](references/API.md).

## Core workflow

1. Install the package:

   ```bash
   pip install behaviorweave
   ```

2. Define policies. A policy maps a pattern count to an intervention; several rules on one
   pattern form an escalation ladder:

   ```python
   from behaviorweave import BehaviorEngine, InterventionType, PolicyRule

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
   ```

3. Report activity where it happens:
   - **LangChain `create_agent`, including Deep Agents:** add
     `BehaviorWeaveMiddleware(engine)` to `middleware=[...]`. It reports every tool call,
     appends guidance to tool results, blocks `stop` and `pause` decisions before the tool
     runs, and records success and failure outcomes.
   - **LangGraph graphs:** build events with `LangGraphEventAdapter` inside nodes (`node`,
     `handoff`, `delegation`, `outcome`) and route on the decision in a conditional edge.
   - **MCP servers:** process `BehaviorEvent.tool_call(...)` inside each tool handler.
   - **langgraph-xai provenance:** map recorded canonical events with
     `LangGraphXAIEventAdapter().event(record, scope=...)`.
   - **Custom loops:** build events with `LangChainEventAdapter` or the `BehaviorEvent`
     factories and call `engine.process(event)`.
4. Apply decisions. `decision.actionable` is `False` for `noop`,
   `decision.intervention.kind.is_terminal` is `True` for `stop` and `pause`, and
   `decision.duplicate` marks a redelivered event whose side effects must not be repeated.
5. Test the policies with [assets/test_behavior_policy.py](assets/test_behavior_policy.py),
   run the project's tests, then run `python scripts/verify_setup.py` again.

## Choose the pattern

| Behavior | Pattern ID |
| --- | --- |
| The same tool with the same arguments, again and again | `repeated_tool_call` |
| A graph node or agent step that loops | `repeated_node_execution`, or `event_frequency` for a total budget |
| Failures or retries that keep accumulating | `failure_streak` or `retry_streak` (a success resets both) |
| Delegating to the same agent repeatedly | `delegation_streak` |
| Two agents handing work back and forth | `oscillation` |
| Anything else | A configured `ConsecutivePattern`, `StreakPattern`, `OscillationPattern`, or `FrequencyPattern`, or the `Pattern` protocol |

## Rules

- **Decisions are requests.** The host decides what each intervention means; never make
  BehaviorWeave reroute, mutate, or stop a graph behind the application's back.
- **Scope deliberately.** Use one stable scope per conversation, thread, run, or
  tenant-qualified session. The middleware uses the LangGraph `thread_id` and raises
  `EventValidationError` when there is none and no `scope` is configured. Never share one
  scope between unrelated conversations.
- **Let the engine count.** Do not keep ad hoc counters, prompt-only "do not repeat"
  instructions, or copies of built-in detectors beside the engine.
- **Respect idempotency.** Reuse an `event_id` only to redeliver the same observation. A
  redelivered event that a policy's pattern recorded changes no state and repeats its
  original intervention with `duplicate=True`. Skip repeated external side effects, such as
  paging an operator, for duplicates, but never skip `interrupt()`: a resumed step runs the
  hook again, and `interrupt()` returns the reviewer's answer only when it is called again.
- **Let configuration errors surface.** Unknown or duplicate pattern and policy IDs,
  thresholds below 1, non-positive cooldowns, and `noop` rules raise
  `PolicyConfigurationError` at construction. Do not catch and ignore it.
- **Keep secrets out of events.** Tool arguments are fingerprinted with SHA-256, but the
  event's `metadata["arguments"]` keeps them for audit sinks. Redact sensitive arguments, and
  never put credentials or model reasoning in metadata.
- **Treat state as opaque.** Never parse or construct state-store keys; use
  `store.clear(scope)` to release a finished conversation and `InMemoryBehaviorStateStore(ttl=...)`
  to bound memory.
- **Stay at the integration boundary.** Do not modify the installed package; configure or
  implement its public classes and protocols instead.

## Human review, pauses, and halts

- Raise from `on_decision`, or call LangGraph's `interrupt()` in it, to pause a run for a
  `human_review` decision on a tool call; compile the agent with a checkpointer so the run
  can resume. On resume the step runs again, the hook receives the same decision, and
  `interrupt()` returns the reviewer's answer.
- `block_on` (default: `stop` and `pause`) refuses a tool call before it runs and returns an
  error `ToolMessage` with the guidance.
- When an outcome triggers a blocking decision, the tool already ran, so the middleware halts
  the scope instead: later tool calls in that scope are refused until
  `middleware.release(scope)` is called. To pause for an operator, call `interrupt()` from
  `on_decision`, and call `release(scope)` from the application before resuming the run.
  Resuming runs the tool again, and a changed outcome is recorded like any other.

## When something is wrong

Start with [references/TROUBLESHOOTING.md](references/TROUBLESHOOTING.md). Common causes:

- **An intervention never fires:** the policy references a pattern that never sees the event
  (wrong event type or outcome), arguments differ between calls, scopes differ between calls,
  or a cooldown or `once_only` rule withholds it (`decision.suppressed` is `True`).
- **`BehaviorWeaveMiddleware needs a scope`:** invoke the agent with
  `config={"configurable": {"thread_id": ...}}` or pass `scope=`.
- **Every tool call is refused:** the scope is halted after a blocking outcome decision;
  call `release(scope)` from the application once the cause is handled, before resuming a
  paused run.

## References

- [references/API.md](references/API.md): public imports, signatures, defaults, and
  decision fields.
- [references/RECIPES.md](references/RECIPES.md): complete patterns for common integration
  tasks.
- [references/TROUBLESHOOTING.md](references/TROUBLESHOOTING.md): symptoms, causes, and
  fixes.
- Documentation: <https://behaviorweave.readthedocs.io>
