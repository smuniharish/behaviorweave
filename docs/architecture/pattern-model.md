# Pattern model

Patterns are composable detectors implementing a small protocol. Built-ins cover
consecutive repeats, outcome streaks, sequences, oscillation, handoff loops,
frequency, thresholds, inactivity, and delegation. A detector receives the current
event plus bounded state and returns an observation; it never chooses an intervention.

