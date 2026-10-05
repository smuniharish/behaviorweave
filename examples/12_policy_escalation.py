"""Escalate progressively: nudge, warn, request human review, then stop.

Four rules on one pattern form an escalation ladder. The ``on_decision`` hook shows where a
host would act on each rung, for example by paging an operator on ``human_review``.

Run:
    uv sync --group examples
    uv run python examples/12_policy_escalation.py
"""

from langchain.tools import tool

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionDecision,
    InterventionType,
    PolicyRule,
)
from common import ask, guarded_agent, print_run


@tool
def run_expensive_report(region: str) -> str:
    """Run the quarterly cost report for one region."""
    return f"Cost report for {region}: spend is 4% over budget."


def on_decision(decision: InterventionDecision, event: BehaviorEvent) -> None:
    if decision.actionable:
        print(
            f"[host] {decision.intervention.kind.value} from policy "
            f"{decision.intervention.policy} after {event.tool_name}"
        )
    if decision.intervention.kind is InterventionType.HUMAN_REVIEW:
        print("[host] paging the on-call analyst for review")


def main() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
            PolicyRule("warning", "repeated_tool_call", 3, InterventionType.WARNING),
            PolicyRule("review", "repeated_tool_call", 4, InterventionType.HUMAN_REVIEW),
            PolicyRule(
                "stop",
                "repeated_tool_call",
                5,
                InterventionType.STOP,
                message="Report blocked after repeated identical runs.",
            ),
        ]
    )
    agent = guarded_agent(engine, [run_expensive_report], on_decision=on_decision)
    result = ask(
        agent,
        "Run run_expensive_report for region EMEA five times, one call at a time, and report "
        "the guidance you received after each call.",
        thread_id="example-12",
    )
    print_run(result)


if __name__ == "__main__":
    main()
