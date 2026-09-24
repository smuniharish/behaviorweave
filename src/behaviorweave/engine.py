from __future__ import annotations

from collections.abc import Iterable

from .events import BehaviorEvent
from .interventions import Intervention, InterventionDecision, InterventionType
from .patterns import Pattern, built_in_patterns
from .policies import PolicyEngine, PolicyRule
from .state import BehaviorStateStore, InMemoryBehaviorStateStore, with_cooldown


class BehaviorEngine:
    def __init__(
        self,
        *,
        policies: Iterable[PolicyRule] = (),
        patterns: Iterable[Pattern] | None = None,
        state_store: BehaviorStateStore | None = None,
    ) -> None:
        self.store = state_store or InMemoryBehaviorStateStore()
        self.patterns = tuple(patterns or built_in_patterns())
        self.policy_engine = PolicyEngine(policies)
        self._rules = self.policy_engine.rules

    def process(self, event: BehaviorEvent) -> InterventionDecision:
        decisions: list[InterventionDecision] = []
        for pattern in self.patterns:
            if pattern.matches(event):
                observation = pattern.observe(event, self.store)
                decision = self.policy_engine.evaluate(observation)
                decisions.append(decision)
                if decision.intervention.kind is not InterventionType.NOOP:
                    rule = next(
                        (r for r in self._rules if r.policy_id == decision.intervention.policy),
                        None,
                    )
                    if rule and rule.cooldown:
                        state = self.store.get(observation.state_key)
                        if state:
                            self.store.put(
                                observation.state_key,
                                with_cooldown(
                                    state, event.timestamp + rule.cooldown, rule.policy_id
                                ),
                            )
        if not decisions:
            return InterventionDecision(intervention=Intervention(InterventionType.NOOP))
        return max(
            decisions,
            key=lambda d: (
                d.intervention.kind in {InterventionType.STOP, InterventionType.PAUSE},
                d.intervention.kind is not InterventionType.NOOP,
                d.explanation.count if d.explanation else 0,
            ),
        )
