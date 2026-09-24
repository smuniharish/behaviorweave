"""Live agent triggering retry-loop thresholds through actual tool calls."""

from common import run_live_behavior_scenario

from behaviorweave import EventType, InterventionType, Outcome, PolicyRule

if __name__ == "__main__":
    run_live_behavior_scenario(
        scenario="retry-loop",
        event_type=EventType.RETRY,
        outcome=Outcome.RETRY,
        policies=[
            PolicyRule("retry-nudge", "retry_streak", 3, InterventionType.NUDGE),
            PolicyRule("retry-stop", "retry_streak", 5, InterventionType.STOP),
        ],
        prompt=(
            "Call record_scenario_action five times with action 'retry-payment-provider'. "
            "Stop when the tool returns BehaviorWeave guidance and summarize it."
        ),
    )
