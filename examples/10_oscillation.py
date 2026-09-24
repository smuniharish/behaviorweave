"""Live agent recording real handoff actions for an oscillation policy scenario."""

from common import run_live_behavior_scenario

from behaviorweave import EventType, InterventionType, PolicyRule

if __name__ == "__main__":
    run_live_behavior_scenario(
        scenario="handoff-loop",
        event_type=EventType.AGENT_HANDOFF,
        policies=[PolicyRule("handoff-warning", "event_frequency", 5, InterventionType.WARNING)],
        prompt=(
            "Call record_scenario_action in order with analyst, researcher, analyst, researcher, "
            "analyst. Then summarize the warning."
        ),
    )
