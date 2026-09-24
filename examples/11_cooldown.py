"""Live agent demonstrating cooldown suppression at a real tool boundary."""

from datetime import timedelta

from common import run_live_behavior_scenario

from behaviorweave import EventType, InterventionType, PolicyRule

if __name__ == "__main__":
    run_live_behavior_scenario(
        scenario="cooldown",
        event_type=EventType.NODE_EXECUTION,
        policies=[
            PolicyRule(
                "cooldown-nudge",
                "repeated_node_execution",
                2,
                InterventionType.NUDGE,
                cooldown=timedelta(minutes=1),
            )
        ],
        prompt=(
            "Call record_scenario_action four times with action 'reconcile-inventory'. "
            "Describe that later interventions are suppressed by the cooldown."
        ),
    )
