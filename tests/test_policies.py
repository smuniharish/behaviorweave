from datetime import timedelta

import pytest

from behaviorweave import (
    BehaviorState,
    InterventionType,
    PatternObservation,
    PolicyConfigurationError,
    PolicyEngine,
    PolicyRule,
)
from support import at


def _observation(
    count: int,
    *,
    pattern_id: str = "p",
    accepted: bool = True,
    history: tuple[str, ...] = (),
    cooldowns: dict | None = None,
) -> PatternObservation:
    state = BehaviorState(
        pattern_id=pattern_id,
        scope="s",
        count=count,
        last_seen=at(0),
        intervention_history=history,
        cooldowns=cooldowns or {},
    )
    return PatternObservation(pattern_id, "s", "fp", "key", count, accepted, state, "observed")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"policy_id": ""}, "policy_id"),
        ({"pattern_id": " "}, "pattern_id"),
        ({"threshold": 0}, "threshold"),
        ({"threshold": -3}, "threshold"),
        ({"threshold": True}, "threshold"),
        ({"threshold": 1.5}, "threshold"),
        ({"priority": "high"}, "priority"),
        ({"priority": False}, "priority"),
        ({"intervention": "explode"}, "unknown intervention"),
        ({"intervention": InterventionType.NOOP}, "noop"),
        ({"cooldown": timedelta(0)}, "cooldown"),
        ({"cooldown": timedelta(seconds=-1)}, "cooldown"),
        ({"cooldown": 30}, "cooldown"),
    ],
)
def test_rule_validation(kwargs: dict[str, object], message: str) -> None:
    fields: dict[str, object] = {
        "policy_id": "rule",
        "pattern_id": "p",
        "threshold": 1,
        "intervention": InterventionType.NUDGE,
        **kwargs,
    }
    with pytest.raises(PolicyConfigurationError, match=message):
        PolicyRule(**fields)  # type: ignore[arg-type]


def test_rule_coerces_intervention_strings() -> None:
    rule = PolicyRule("r", "p", 1, "stop")  # type: ignore[arg-type]
    assert rule.intervention is InterventionType.STOP
    assert rule.intervention.is_terminal
    assert not InterventionType.NUDGE.is_terminal


def test_engine_rejects_invalid_rule_sets() -> None:
    with pytest.raises(PolicyConfigurationError, match="expected PolicyRule"):
        PolicyEngine(["not a rule"])  # type: ignore[list-item]
    rule = PolicyRule("dup", "p", 1, InterventionType.NUDGE)
    with pytest.raises(PolicyConfigurationError, match="duplicate policy_id"):
        PolicyEngine([rule, PolicyRule("dup", "q", 2, InterventionType.STOP)])


def test_pattern_ids_and_rules() -> None:
    rules = [
        PolicyRule("a", "p", 1, InterventionType.NUDGE),
        PolicyRule("b", "q", 1, InterventionType.NUDGE),
    ]
    engine = PolicyEngine(rules)
    assert engine.rules == tuple(rules)
    assert engine.pattern_ids == frozenset({"p", "q"})


def test_duplicate_and_unmatched_observations_are_noops() -> None:
    engine = PolicyEngine([PolicyRule("a", "p", 2, InterventionType.NUDGE)])
    duplicate = engine.evaluate(_observation(5, accepted=False))
    assert duplicate.duplicate
    assert not duplicate.actionable
    assert duplicate.intervention.reason == "redelivered event; no state changed"
    below = engine.evaluate(_observation(1))
    assert not below.actionable
    assert below.explanation is None
    assert not below.suppressed
    other = engine.evaluate(_observation(9, pattern_id="unrelated"))
    assert other.intervention.kind is InterventionType.NOOP


def test_actionable_decision_carries_message_reason_and_explanation() -> None:
    rule = PolicyRule(
        "a", "p", 2, InterventionType.WARNING, message="Slow down.", severity="warning"
    )
    decision = PolicyEngine([rule]).evaluate(_observation(3))
    intervention = decision.intervention
    assert intervention.kind is InterventionType.WARNING
    assert (intervention.message, intervention.reason) == ("Slow down.", "observed")
    assert (intervention.policy, intervention.pattern, intervention.scope) == ("a", "p", "s")
    assert intervention.severity == "warning"
    assert decision.explanation is not None
    assert (decision.explanation.count, decision.explanation.threshold) == (3, 2)
    assert decision.explanation.reason == "observed"


@pytest.mark.parametrize(
    ("rules", "winner"),
    [
        (
            [
                PolicyRule("low", "p", 1, InterventionType.STOP),
                PolicyRule("high", "p", 1, InterventionType.NUDGE, priority=1),
            ],
            "high",
        ),
        (
            [
                PolicyRule("first", "p", 1, InterventionType.NUDGE),
                PolicyRule("deeper", "p", 2, InterventionType.NUDGE),
            ],
            "deeper",
        ),
        (
            [
                PolicyRule("warn", "p", 2, InterventionType.WARNING),
                PolicyRule("pause", "p", 2, InterventionType.PAUSE),
            ],
            "pause",
        ),
        (
            [
                PolicyRule("first", "p", 2, InterventionType.WARNING),
                PolicyRule("second", "p", 2, InterventionType.NUDGE),
            ],
            "first",
        ),
        (
            [
                PolicyRule("eligible", "p", 2, InterventionType.NUDGE),
                PolicyRule("not-yet", "p", 9, InterventionType.STOP, priority=5),
            ],
            "eligible",
        ),
    ],
)
def test_rule_precedence(rules: list[PolicyRule], winner: str) -> None:
    assert PolicyEngine(rules).evaluate(_observation(2)).intervention.policy == winner


def test_once_only_rules_are_suppressed_after_firing() -> None:
    engine = PolicyEngine([PolicyRule("once", "p", 1, InterventionType.NUDGE, once_only=True)])
    decision = engine.evaluate(_observation(2, history=("once",)))
    assert decision.suppressed
    assert not decision.actionable
    assert decision.intervention.policy == "once"
    assert decision.explanation is not None
    assert decision.explanation.reason == "once-only policy 'once' already fired"


def test_cooldown_suppresses_only_until_it_expires() -> None:
    rule = PolicyRule("cool", "p", 1, InterventionType.NUDGE, cooldown=timedelta(seconds=30))
    engine = PolicyEngine([rule])
    active = engine.evaluate(_observation(2, cooldowns={"cool": at(30)}))
    assert active.suppressed
    assert "cooling down until" in active.intervention.reason
    expired = engine.evaluate(_observation(2, cooldowns={"cool": at(0)}))
    assert expired.actionable
    other_policy = engine.evaluate(_observation(2, cooldowns={"other": at(99)}))
    assert other_policy.actionable


def test_evaluation_is_pure() -> None:
    engine = PolicyEngine([PolicyRule("once", "p", 1, InterventionType.NUDGE, once_only=True)])
    observation = _observation(1)
    assert engine.evaluate(observation).actionable
    assert engine.evaluate(observation).actionable
    assert observation.state.intervention_history == ()
