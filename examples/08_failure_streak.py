"""Escalate a failure streak detected from real tool results.

The middleware records every tool result as a success or failure outcome. When the flaky
database tool fails three times in a row, BehaviorWeave appends an escalation instruction and
the ``on_decision`` hook notifies an operator. A fifth identical retry is blocked outright.

Run:
    uv sync --group examples
    uv run python examples/08_failure_streak.py
"""

from langchain.tools import tool
from langchain_core.tools import ToolException

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionDecision,
    InterventionType,
    PolicyRule,
)
from common import ask, guarded_agent, print_run


@tool
def query_inventory(sku: str) -> str:
    """Query the inventory database for one SKU."""
    raise ToolException(f"Database timeout while reading {sku}.")


# Return tool failures to the model as error results instead of aborting the run.
query_inventory.handle_tool_error = True


def notify_operator(decision: InterventionDecision, event: BehaviorEvent) -> None:
    if decision.intervention.kind is InterventionType.ESCALATE:
        print(f"[operator page] {decision.intervention.reason} in {event.scope}")


def main() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "failure-escalate",
                "failure_streak",
                3,
                InterventionType.ESCALATE,
                message="The database keeps failing. Stop retrying and report the outage.",
            ),
            PolicyRule(
                "retry-backstop",
                "repeated_tool_call",
                5,
                InterventionType.STOP,
                message="Retry limit reached. Report the outage now.",
            ),
        ]
    )
    agent = guarded_agent(engine, [query_inventory], on_decision=notify_operator)
    result = ask(
        agent,
        "Look up SKU A-100. If the query fails, retry it until it succeeds.",
        thread_id="example-08",
    )
    print_run(result)


if __name__ == "__main__":
    main()
