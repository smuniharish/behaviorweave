"""Behavior-policy tests to copy into your project's test suite.

Replace ``build_engine`` with the factory your application uses, and adjust the expectations
to your policies. The tests pin timestamps, so cooldowns are deterministic, and they check
what must happen as well as what must not: no intervention before a threshold, no leakage
between scopes, and no double counting of redelivered events.

The tests run with plain pytest.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionType,
    Outcome,
    PolicyRule,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def build_engine() -> BehaviorEngine:
    """Return a fresh engine configured like the application's. Replace this function."""
    return BehaviorEngine(
        policies=[
            PolicyRule(
                "repeat-nudge",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                message="Reuse the result you already have.",
            ),
            PolicyRule("repeat-stop", "repeated_tool_call", 3, InterventionType.STOP),
            PolicyRule(
                "outage",
                "failure_streak",
                3,
                InterventionType.ESCALATE,
                cooldown=timedelta(minutes=10),
            ),
        ]
    )


def call(engine: BehaviorEngine, scope: str = "conversation-1", **arguments: object) -> str:
    """Process one ``search`` tool call and return the decision's kind."""
    event = BehaviorEvent.tool_call("search", arguments or {"q": "status"}, scope=scope)
    return engine.process(event).intervention.kind.value


def failure(engine: BehaviorEngine, minute: int) -> str:
    """Process one failure outcome at a fixed time and return the decision's kind."""
    event = BehaviorEvent.outcome_event(
        Outcome.FAILURE, scope="service", timestamp=T0 + timedelta(minutes=minute)
    )
    return engine.process(event).intervention.kind.value


def test_identical_calls_escalate_from_nudge_to_stop() -> None:
    engine = build_engine()

    assert [call(engine) for _ in range(3)] == ["noop", "nudge", "stop"]


def test_calls_with_different_arguments_are_not_repeats() -> None:
    engine = build_engine()

    assert [call(engine, q=f"page {page}") for page in range(3)] == ["noop"] * 3


def test_scopes_never_share_history() -> None:
    engine = build_engine()

    assert [call(engine, scope=f"conversation-{n}") for n in range(3)] == ["noop"] * 3


def test_a_redelivered_event_repeats_its_decision_without_counting_again() -> None:
    engine = build_engine()
    event = BehaviorEvent.tool_call("search", {"q": "status"}, scope="conversation-1")
    engine.process(BehaviorEvent.tool_call("search", {"q": "status"}, scope="conversation-1"))
    first = engine.process(event)

    again = engine.process(event)

    assert again.duplicate
    assert again.intervention == first.intervention
    assert call(engine) == "stop", "the next new call continues the count"


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        ((0, 1, 2), ["noop", "noop", "escalate"]),
        ((0, 1, 2, 3), ["noop", "noop", "escalate", "noop"]),
        ((0, 1, 2, 30), ["noop", "noop", "escalate", "escalate"]),
    ],
)
def test_a_failure_streak_escalates_once_per_cooldown(
    minutes: tuple[int, ...], expected: list[str]
) -> None:
    engine = build_engine()

    assert [failure(engine, minute) for minute in minutes] == expected
