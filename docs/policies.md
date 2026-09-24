# Policies and interventions

`PolicyRule` maps a pattern threshold to an `InterventionType`. Rules are evaluated
deterministically by priority and threshold. Terminal decisions (`STOP`, `PAUSE`) win
ties. `once_only` and `cooldown` prevent repeated emissions.

BehaviorWeave emits `NOOP`, `NUDGE`, `WARNING`, `REDIRECT`, `RETRY`, `ESCALATE`,
`HUMAN_REVIEW`, `FORCE_SYNTHESIS`, `PAUSE`, `STOP`, and `CUSTOM`; it never executes
arbitrary host actions.
