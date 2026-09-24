# Patterns

Built-in detectors include repeated tool and node execution, failure/retry/success
streaks, delegation streaks, and bounded frequency observations. Custom detectors
implement `matches(event)` and `observe(event, store)` and can be passed to
`BehaviorEngine(patterns=...)`.

V1 fingerprints are deterministic and structural. Semantic equivalence is intentionally
not implemented.
