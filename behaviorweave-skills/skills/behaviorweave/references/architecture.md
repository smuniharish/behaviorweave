# BehaviorWeave architecture

BehaviorWeave is a deterministic behavioral policy layer for agent runtimes. It normalizes observable events, tracks scoped state, detects patterns, evaluates policies, and returns an intervention decision.

The runtime boundary is intentionally narrow:

- `BehaviorEvent` captures structured observations such as tool calls, node execution, outcomes, retries, and delegation.
- `BehaviorState` stores per-pattern, per-scope history and cooldown metadata.
- `Pattern` detectors convert runtime events into `PatternObservation` values.
- `PolicyRule` maps a pattern and threshold to an `InterventionType`.
- `BehaviorEngine.process()` applies the configured patterns and returns the strongest decision for the current event.

Key design constraints:

- BehaviorWeave does not execute tool calls or mutate graph flow on its own.
- It evaluates deterministic rules and emits a decision that the host runtime can enforce.
- State is scoped and explicit; the same pattern should be tracked independently for each thread, run, or application-scoped identifier.
- The library deliberately avoids prompt-only heuristics and semantic guessing.

See the package docs in [BehaviorWeave documentation](https://behaviorweave.readthedocs.io/en/latest/) and the [architecture overview](https://behaviorweave.readthedocs.io/en/latest/architecture/overview/) for the full design and decision model.
