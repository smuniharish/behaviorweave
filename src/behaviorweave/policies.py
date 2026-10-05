"""Policy rules and deterministic policy evaluation.

A policy answers *what should happen*: it maps a pattern count to an intervention, subject to
precedence, cooldowns, and once-only semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .errors import PolicyConfigurationError
from .interventions import Explanation, Intervention, InterventionDecision, InterventionType
from .patterns import PatternObservation
from .state import BehaviorState

__all__ = ["PolicyEngine", "PolicyRule"]


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """Maps a pattern threshold to an intervention.

    Attributes:
        policy_id: Unique, stable identifier recorded in decisions.
        pattern_id: ID of the pattern this rule governs, such as ``"repeated_tool_call"``.
        threshold: Minimum pattern count (at least 1) at which the rule applies.
        intervention: Action requested when the rule applies. Must not be `noop`.
        priority: Precedence among applicable rules; higher wins. Defaults to 0.
        cooldown: Optional positive period after this policy fires during which it is
            suppressed. Other policies are unaffected, so escalation still happens.
        once_only: When ``True``, this policy fires at most once per pattern history.
        message: Instruction for the agent or operator, returned as the intervention message.
        severity: Application-defined severity label copied to the intervention.

    ``cooldown`` and ``once_only`` are tracked per pattern history: per scope for consecutive,
    streak, and oscillation patterns, and per scope and event identity for frequency patterns.

    Raises:
        PolicyConfigurationError: If any field is invalid.
    """

    policy_id: str
    pattern_id: str
    threshold: int
    intervention: InterventionType
    priority: int = 0
    cooldown: timedelta | None = None
    once_only: bool = False
    message: str | None = None
    severity: str = "info"

    def __post_init__(self) -> None:
        for name in ("policy_id", "pattern_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PolicyConfigurationError(f"{name} must be a non-empty string")
        if not _is_int(self.threshold) or self.threshold < 1:
            raise PolicyConfigurationError(
                f"policy {self.policy_id!r}: threshold must be an integer >= 1"
            )
        if not _is_int(self.priority):
            raise PolicyConfigurationError(
                f"policy {self.policy_id!r}: priority must be an integer"
            )
        try:
            intervention = InterventionType(self.intervention)
        except ValueError:
            raise PolicyConfigurationError(
                f"policy {self.policy_id!r}: unknown intervention {self.intervention!r}"
            ) from None
        if intervention is InterventionType.NOOP:
            raise PolicyConfigurationError(
                f"policy {self.policy_id!r}: a policy cannot request 'noop'; omit the rule instead"
            )
        object.__setattr__(self, "intervention", intervention)
        if self.cooldown is not None and (
            not isinstance(self.cooldown, timedelta) or self.cooldown <= timedelta(0)
        ):
            raise PolicyConfigurationError(
                f"policy {self.policy_id!r}: cooldown must be a positive timedelta or None"
            )


class PolicyEngine:
    """Evaluates pattern observations against policy rules.

    When several rules of one pattern apply, the winner is chosen by, in order: higher
    ``priority``, higher ``threshold``, terminal interventions (`stop`, `pause`), and earlier
    declaration.

    Args:
        rules: Rules available for evaluation. Policy IDs must be unique.

    Raises:
        PolicyConfigurationError: If an item is not a ``PolicyRule`` or a policy ID repeats.
    """

    def __init__(self, rules: Iterable[PolicyRule] = ()) -> None:
        self.rules: tuple[PolicyRule, ...] = tuple(rules)
        seen: set[str] = set()
        for rule in self.rules:
            if not isinstance(rule, PolicyRule):
                raise PolicyConfigurationError(f"expected PolicyRule, got {type(rule).__name__}")
            if rule.policy_id in seen:
                raise PolicyConfigurationError(f"duplicate policy_id {rule.policy_id!r}")
            seen.add(rule.policy_id)
        grouped: dict[str, list[PolicyRule]] = {}
        for rule in self.rules:
            grouped.setdefault(rule.pattern_id, []).append(rule)
        # Stable descending sort: the first rule whose threshold is met has the highest precedence.
        self._by_pattern: dict[str, tuple[PolicyRule, ...]] = {
            pattern_id: tuple(
                sorted(
                    group,
                    key=lambda r: (r.priority, r.threshold, r.intervention.is_terminal),
                    reverse=True,
                )
            )
            for pattern_id, group in grouped.items()
        }

    @property
    def pattern_ids(self) -> frozenset[str]:
        """IDs of every pattern referenced by at least one rule."""
        return frozenset(self._by_pattern)

    def evaluate(self, observation: PatternObservation) -> InterventionDecision:
        """Return the decision for one observation.

        A rule withheld by its cooldown or by ``once_only`` produces a `noop` marked
        ``suppressed`` with an explanation. An observation of a redelivered event
        (``observation.accepted`` is ``False``) produces a `noop` marked ``duplicate``;
        [`BehaviorEngine.process`][behaviorweave.BehaviorEngine.process] instead repeats the
        decision originally made for that event when it was actionable. Evaluation never
        changes state.
        """
        return self._select(observation)[1]

    def _select(
        self, observation: PatternObservation
    ) -> tuple[PolicyRule | None, InterventionDecision]:
        if not observation.accepted:
            return None, InterventionDecision(
                Intervention(
                    InterventionType.NOOP,
                    reason="redelivered event; no state changed",
                    pattern=observation.pattern_id,
                    scope=observation.scope,
                ),
                duplicate=True,
            )
        rule = next(
            (
                candidate
                for candidate in self._by_pattern.get(observation.pattern_id, ())
                if observation.count >= candidate.threshold
            ),
            None,
        )
        if rule is None:
            return None, InterventionDecision(
                Intervention(
                    InterventionType.NOOP, pattern=observation.pattern_id, scope=observation.scope
                )
            )
        suppression = _suppression_reason(rule, observation.state, observation.state.last_seen)
        if suppression is not None:
            return rule, InterventionDecision(
                Intervention(
                    InterventionType.NOOP,
                    reason=suppression,
                    pattern=rule.pattern_id,
                    policy=rule.policy_id,
                    scope=observation.scope,
                ),
                Explanation(
                    observation.pattern_id,
                    observation.count,
                    rule.threshold,
                    rule.policy_id,
                    suppression,
                ),
                suppressed=True,
            )
        return rule, _decision(
            rule,
            pattern_id=observation.pattern_id,
            scope=observation.scope,
            count=observation.count,
            reason=observation.reason,
        )


def _decision(
    rule: PolicyRule,
    *,
    pattern_id: str,
    scope: str,
    count: int,
    reason: str,
    duplicate: bool = False,
) -> InterventionDecision:
    """Build the actionable decision ``rule`` produces for an observation."""
    return InterventionDecision(
        Intervention(
            rule.intervention,
            message=rule.message,
            reason=reason,
            pattern=rule.pattern_id,
            policy=rule.policy_id,
            scope=scope,
            severity=rule.severity,
        ),
        Explanation(pattern_id, count, rule.threshold, rule.policy_id, reason),
        duplicate=duplicate,
    )


def _suppression_reason(rule: PolicyRule, state: BehaviorState, now: datetime | None) -> str | None:
    """Return why ``rule`` is currently withheld for ``state``, or ``None`` if it may fire."""
    if rule.once_only and rule.policy_id in state.intervention_history:
        return f"once-only policy {rule.policy_id!r} already fired"
    until = state.cooldowns.get(rule.policy_id)
    if until is not None and now is not None and until > now:
        return f"policy {rule.policy_id!r} is cooling down until {until.isoformat()}"
    return None


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
