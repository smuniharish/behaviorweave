# Changelog

All notable changes to BehaviorWeave are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-04

The first stable release. It adds a LangChain agent middleware, an oscillation detector, and
idempotent event delivery; targets langgraph-xai 1.0 and Python 3.12 to 3.14; and fixes
several policy and state bugs from 0.1. Some fixes change observable behavior, so review
[Upgrading from 0.1](#upgrading-from-01) before upgrading.

### Added

- `BehaviorWeaveMiddleware`, a LangChain v1 agent middleware that guards every tool call:
  it appends guidance, blocks `stop` and `pause` decisions, records success and failure
  outcomes, halts a scope when an outcome triggers a blocking decision (lifted with
  `release(scope)`), re-applies the original tool-call decision when a graph step is
  replayed or resumed, and supports sync and async agents, including Deep Agents.
- Built-in `oscillation` pattern detecting agents that hand work back and forth.
- Public pattern classes exported from the package root: `ConsecutivePattern`,
  `StreakPattern`, `OscillationPattern`, `FrequencyPattern`, and the `Pattern` protocol.
- `audit_sink` on `BehaviorEngine`, delivering an `AuditRecord` for every processed event.
- Error hierarchy: `BehaviorWeaveError`, `EventValidationError`,
  `PolicyConfigurationError`, and `StateStoreError`, all compatible with `ValueError`.
- `InterventionDecision.duplicate`, `InterventionDecision.actionable`, and
  `InterventionType.is_terminal`.
- `BehaviorState.to_dict`, `to_json`, `from_dict`, and `from_json` for durable stores, and
  `BehaviorState.emissions`, which records recent decisions for idempotent redelivery.
- `InMemoryBehaviorStateStore` gains a `clock` argument, `purge_expired()`, and
  `clear(scope=None)`; expired entries are also purged periodically.
- Event factories accept `timestamp`, `thread_id`, `run_id`, `metadata`, and
  `provenance_ref`; `outcome_event` also accepts `tool_name` and `node_name`.
- `LangChainEventAdapter.tool_end`, plus tool names and event IDs on every adapter method.
- `LangGraphEventAdapter.handoff` and `LangGraphEventAdapter.delegation`.
- `LangGraphXAIEventAdapter.instrument_graph(runtime=...)` to query and close your own
  provenance runtime.
- Support for Python 3.13 and 3.14.
- An [Agent Skill](https://agentskills.io/) that teaches coding agents to integrate, tune,
  and test BehaviorWeave, with a setup check and a test template.

### Changed

- Requires `langchain` 1.4.3, `langgraph` 1.2.12, and `langgraph-xai` 1.0.0 or later, each
  below 2.0.
- `LangGraphXAIEventAdapter` maps the langgraph-xai 1.0 event schema: the canonical `id`
  becomes the event ID and the default `provenance_ref`, and node events are named by their
  `node_id`. Cancelled or interrupted nodes and tools, and cancelled runs, carry no outcome,
  so they neither extend nor reset a streak.
- More than 20 times higher throughput and bounded memory: only patterns referenced by a
  policy are evaluated, state snapshots are immutable and shared without deep copies, and
  state keys no longer grow with argument size.
- Cooldowns are tracked per policy and measured in event time.
- `Intervention.reason` always describes the observed behavior; the policy's instruction is
  in `Intervention.message`.
- Tool-call fingerprints have the form `tool_name#<digest>`.
- `PolicyRule` validates its fields: thresholds must be at least 1, rules cannot request
  `noop`, and cooldowns must be positive. Policy and pattern IDs must be unique.
- Examples run against any OpenAI-compatible endpoint through `OPENAI_API_KEY`,
  `BEHAVIORWEAVE_MODEL`, and `OPENAI_BASE_URL`, and showcase the middleware.
- Documentation was rewritten, with rendered architecture, sequence, and decision diagrams
  and a generated API reference.

### Removed

- `FrequencyPattern.window_size` (it was never applied) and `ConsecutivePattern.identity_field`.
- `ConsecutivePattern.outcome`; use `StreakPattern` for outcomes.
- `BehaviorState.threshold_state`, `window_start`, `window_end`, and `cooldown_until`.
- `BehaviorState.json()`; use `to_json()`.
- `PatternObservation.crossed`; use `accepted`.
- The internal helpers `state.advance_state` and `state.with_cooldown`.
- The published `dev`, `examples`, `mcp`, and `real-model` extras.
- Support for langgraph-xai 0.x event payloads (`event_id` and `node.node_name`).

### Fixed

- `once_only` policies fired on every event unless a cooldown was also configured.
- A cooldown on one policy suppressed every other policy on the same pattern, including a
  later `stop`.
- Recording a cooldown could overwrite concurrent state updates and lose events.
- Cooldowns and once-only history were recorded for decisions that were never returned.
- Failure, retry, and success streaks were not reset by contrary outcomes, and `retry`
  events and retry outcomes formed separate streaks.
- Redelivered events were evaluated again as new observations. They now change no state and
  repeat the intervention originally decided for them, marked `duplicate`, so a retried or
  resumed step re-applies the same intervention.
- `patterns=[]` silently selected the built-in patterns, and a custom store that evaluated
  as false was silently replaced.
- Policies referencing an unknown pattern were silently ignored; they now raise
  `PolicyConfigurationError`.
- Rule priority was ignored when choosing between decisions of different patterns.
- Tool fingerprints raised on non-JSON arguments and embedded raw argument values.
- Canonical `langgraph-xai` events were all mapped to `custom`; their event IDs, timestamps,
  and outcomes were dropped, and whole payloads were copied into metadata.
- Explanations never carried the triggering event's `provenance_ref`.
- String event types and outcomes passed to `BehaviorEvent` broke identity and matching;
  they are now validated and converted.

### Upgrading from 0.1

| 0.1 | 1.0 |
| --- | --- |
| `BehaviorState.cooldown_until` | `BehaviorState.cooldowns[policy_id]` |
| `BehaviorState.window_start`, `window_end` | `BehaviorState.first_seen`, `last_seen` |
| `BehaviorState.json()` | `BehaviorState.to_json()` |
| `PatternObservation.crossed` | `PatternObservation.accepted` |
| `ConsecutivePattern(id, types, outcome)` | `StreakPattern(id, counts=..., resets=...)` |
| `FrequencyPattern(id, types, window_size=...)` | `FrequencyPattern(id, types)` |
| `except ValueError` around events or policies | Still works; prefer `except BehaviorWeaveError`. |
| Inspecting state for patterns without policies | Add a policy, or call the pattern's `observe` directly. |
| langgraph-xai 0.x events with `event_id` | langgraph-xai 1.0 events; the canonical `id` is the event ID. |
| `uv sync --extra dev` / `--extra real-model` | `uv sync` / `uv sync --group examples` |
| Provider-specific example settings | `OPENAI_API_KEY`, `BEHAVIORWEAVE_MODEL`, `OPENAI_BASE_URL` |

Behavior changes to review:

- A redelivered event changes no state and repeats its original intervention with
  `duplicate=True`; check `decision.duplicate` before repeating external side effects, but
  keep calling `interrupt()` for duplicates in hooks that use it.
- Streak counts reset on contrary outcomes.
- A `once_only` policy fires once per pattern history; frequency histories are per identity.
- Policies with a cooldown no longer mute other policies.

## [0.1.0] - 2026-09-23

Initial release: deterministic behavioral policy core, built-in patterns, in-memory state
store, and LangChain, LangGraph, and langgraph-xai adapters.

[1.0.0]: https://github.com/smuniharish/behaviorweave/releases/tag/v1.0.0
[0.1.0]: https://github.com/smuniharish/behaviorweave/releases/tag/v0.1.0
