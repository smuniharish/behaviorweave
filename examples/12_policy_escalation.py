"""Live agent demonstrating policy escalation at a real tool boundary."""

from common import run_live_behavior_scenario

from behaviorweave import EventType, InterventionType, PolicyRule

if __name__ == "__main__":
    run_live_behavior_scenario(
        scenario="policy-escalation",
        event_type=EventType.NODE_EXECUTION,
        policies=[
            PolicyRule("nudge", "repeated_node_execution", 3, InterventionType.NUDGE),
            PolicyRule("warning", "repeated_node_execution", 4, InterventionType.WARNING),
            PolicyRule("review", "repeated_node_execution", 5, InterventionType.HUMAN_REVIEW),
            PolicyRule("stop", "repeated_node_execution", 6, InterventionType.STOP),
        ],
        prompt=(
            "Call record_scenario_action six times with action 'run-expensive-report'. "
            "After each intervention, report the strongest current guidance."
        ),
    )
