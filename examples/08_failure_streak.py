"""Live agent triggering a failure-streak policy through actual tool calls."""

from common import run_live_behavior_scenario

from behaviorweave import EventType, InterventionType, Outcome, PolicyRule

if __name__ == "__main__":
    run_live_behavior_scenario(
        scenario="failure-streak",
        event_type=EventType.OUTCOME,
        outcome=Outcome.FAILURE,
        policies=[PolicyRule("failure-escalate", "failure_streak", 3, InterventionType.ESCALATE)],
        prompt=(
            "Call record_scenario_action exactly three times with action 'database-timeout'. "
            "Then report the BehaviorWeave guidance."
        ),
    )
