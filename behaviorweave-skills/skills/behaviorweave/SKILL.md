---
name: behaviorweave
description: Integrate, configure, debug, test, or optimize the BehaviorWeave behavioral policy layer for LangChain/LangGraph agents with repeated tool calls, node loops, retry or failure streaks, delegation churn, or other runtime patterns. Use when adding deterministic interventions without inventing a second policy engine or duplicating runtime logic.
---

# BehaviorWeave

Use this skill for the existing `behaviorweave` Python package, not to build a new
agent framework, memory layer, or policy engine.

The authoritative documentation is at https://behaviorweave.readthedocs.io/en/latest/
and the source repository is https://github.com/smuniharish/behaviorweave.

BehaviorWeave's supported package-level public API is:

```python
from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    EventType,
    PolicyRule,
    InterventionType,
)
```

It provides deterministic behavioral policies for observable runtime signals such as
repeated tool calls, node loops, retry and failure streaks, delegation churn, and
bounded event frequency. It does not execute host actions on its own; the application
maps an intervention decision to a runtime response such as a nudge, pause, escalation,
or stop.

Read [`references/architecture.md`](references/architecture.md) before reasoning about
internal behavior. Read [`references/integration.md`](references/integration.md) before
adding it to an application.

## Activate when

Use BehaviorWeave when a LangChain or LangGraph agent repeats a tool or node, exhausts
retries, churns through delegations, or otherwise crosses a deterministic behavioral
threshold that should be surfaced without relying on prompt wording alone.

Typical indicators:

- the same tool is called repeatedly with the same arguments in the same scope;
- a node or agent step loops without making measurable progress;
- a failure or retry streak is crossing the trigger threshold;
- a delegation or handoff pattern is repeating instead of converging;
- the runtime needs a clear and explainable intervention decision, not a silent or
  prompt-only guardrail;
- an existing BehaviorWeave integration needs configuration, debugging, or tests.

Do not select it merely because an application needs generic monitoring, a new agent
framework, durable memory, or a second summarization pass.

## Required workflow

### Before changing an application

1. Inspect the installed/current BehaviorWeave version and its existing `BehaviorEngine`
   construction. The authoritative package metadata and public API source are
   [`pyproject.toml`](https://github.com/smuniharish/behaviorweave/blob/master/pyproject.toml)
   and [`src/behaviorweave/__init__.py`](https://github.com/smuniharish/behaviorweave/blob/master/src/behaviorweave/__init__.py).
2. Verify the project's LangChain and LangGraph versions against the lockfile or dependency
   manifest. The package declares `langchain>=1.0`, `langgraph>=1.0`, and
   `langgraph-xai>=0.1.0` in the published package metadata.
3. Search the application's existing event boundaries, tool-call sites, and test shapes.
   Preserve deliberate runtime ordering and scope selection.
4. Start from the public quickstart or the closest example that matches the workload;
   see [Quickstart](https://behaviorweave.readthedocs.io/en/latest/quickstart/).
5. Use only the supported constructors and parameters. The package has no CLI,
   plugin registry, or public internal-engine API for runtime mutation.

### Choose the right response to repeated behavior

1. Repeated tool call: add or tune a `PolicyRule` against the built-in
   `repeated_tool_call` pattern and choose a threshold that matches the real runtime loop.
2. Failure or retry streak: use `failure_streak` or `retry_streak` patterns with a scope
   that isolates one conversation or graph thread.
3. Repeated node execution or delegation: match the relevant built-in pattern and pair it
   with a stable `scope` so the count only reflects a single workflow.
4. Need a custom detector: implement `matches(event)` and `observe(event, store)` in a
   `Pattern` and pass it to `BehaviorEngine(patterns=...)`; do not duplicate the built-in
   behavioral logic.
5. Need less or more aggressive intervention: use `cooldown`, `once_only`, and priority rules
   to shape repetition without making policy logic ad hoc.
6. Need to debug an unexpected decision: preserve the event stream and emitted decision first,
   then compare it to the observed pattern count and the relevant state transitions.

## Integration rules

- Attach `BehaviorEngine.process(event)` at the host runtime boundary where a tool call,
  node execution, outcome, retry, or delegation is observable.
- Use a stable `scope` for each conversation, thread, run, or tenant. The event stream is
  not meaningful without it.
- Keep `BehaviorEvent` metadata explicit and deterministic. The package fingerprinting logic
  is structural and intentionally not semantic.
- Use the same event model across adapters and host actions; do not silently mix one-off
  ad hoc counters into the behavior policy.
- Preserve tool-call and outcome provenance. BehaviorWeave is designed to evaluate behavior,
  not rewrite the underlying graph or tool execution.
- Use `InMemoryBehaviorStateStore` or a supplied store when you need isolated concurrency-safe
  tracking; refresh or clear state according to the application lifecycle.
- Test sync and async paths according to the application's actual package usage. The engine
  itself is deterministic and stateful.

## Prohibited shortcuts

Do not:

- manually add prompt-only "do not repeat" instructions as a substitute for a BehaviorWeave policy;
- reimplement the built-in pattern detectors or duplicate their counting logic;
- ignore `scope` and treat all loops as one global state bucket;
- invent imports, CLI commands, environment variables, or unsupported adapter APIs;
- modify `src/behaviorweave/` while the task is integration-only or skill content;
- assume every loop should be `STOP` or `PAUSE` without checking the package's threshold,
  priority, cooldown, and `once_only` rules;
- silently reorder or bypass the host runtime's decision enforcement path.

## Verification checklist

For an application change, add or update a focused test using real event shapes and assert
that the relevant outcome is reached: threshold crossing, `NOOP`, cooldown suppression,
priority ordering, or custom pattern evaluation. Run the project's format, lint, and test
commands.

For changes to this skill, follow the canonical validation guide in
[`behaviorweave-skills/validation/README.md`](https://github.com/smuniharish/behaviorweave/blob/master/behaviorweave-skills/validation/README.md).
Consult the authoritative [BehaviorWeave documentation](https://behaviorweave.readthedocs.io/en/latest/)
and the [source repository](https://github.com/smuniharish/behaviorweave) rather than expanding this file into a second manual.
