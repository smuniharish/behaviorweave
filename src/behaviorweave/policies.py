from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from .interventions import Explanation, Intervention, InterventionDecision, InterventionType
from .patterns import PatternObservation


@dataclass(frozen=True, slots=True)
class PolicyRule:
    policy_id: str
    pattern_id: str
    threshold: int
    intervention: InterventionType
    priority: int = 0
    cooldown: timedelta | None = None
    once_only: bool = False
    message: str | None = None
    severity: str = "info"


class PolicyEngine:
    def __init__(self, rules: Iterable[PolicyRule] = ()) -> None:
        self.rules = tuple(rules)

    def evaluate(self, observation: PatternObservation) -> InterventionDecision:
        candidates = [
            r
            for r in self.rules
            if r.pattern_id == observation.pattern_id and observation.count >= r.threshold
        ]
        if not candidates:
            return InterventionDecision(
                Intervention(
                    InterventionType.NOOP, pattern=observation.pattern_id, scope=observation.scope
                )
            )
        rule = max(
            candidates,
            key=lambda r: (
                r.priority,
                r.threshold,
                r.intervention in {InterventionType.STOP, InterventionType.PAUSE},
            ),
        )
        state = observation.state
        already = rule.policy_id in state.intervention_history
        active = (
            state.cooldown_until is not None
            and state.last_seen is not None
            and state.cooldown_until > state.last_seen
        )
        if (rule.once_only and already) or active:
            return InterventionDecision(
                Intervention(
                    InterventionType.NOOP,
                    reason="cooldown or once-only",
                    pattern=rule.pattern_id,
                    policy=rule.policy_id,
                    scope=observation.scope,
                ),
                suppressed=True,
            )
        reason = rule.message or observation.reason
        intervention = Intervention(
            rule.intervention,
            message=rule.message,
            reason=reason,
            pattern=rule.pattern_id,
            policy=rule.policy_id,
            scope=observation.scope,
            severity=rule.severity,
        )
        return InterventionDecision(
            intervention,
            Explanation(
                observation.pattern_id, observation.count, rule.threshold, rule.policy_id, reason
            ),
        )
