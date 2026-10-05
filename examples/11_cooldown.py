"""Use a per-policy cooldown without muting escalation.

The nudge policy has a one-hour cooldown, so it fires once and then stays quiet. The cooldown
belongs to the nudge alone: when the agent keeps repeating the call, the stop policy still
fires and blocks it.

Run:
    uv sync --group examples
    uv run python examples/11_cooldown.py
"""

from datetime import timedelta

from langchain.tools import tool

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from common import ask, guarded_agent, print_run


@tool
def reconcile_inventory(warehouse: str) -> str:
    """Reconcile stock levels for one warehouse."""
    return f"{warehouse}: 3 discrepancies found and corrected."


def main() -> None:
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "repeat-nudge",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                cooldown=timedelta(hours=1),
                message="Reconciliation already ran; its result is still current.",
            ),
            PolicyRule(
                "repeat-stop",
                "repeated_tool_call",
                4,
                InterventionType.STOP,
                message="Reconciliation blocked: it already ran three times.",
            ),
        ]
    )
    agent = guarded_agent(engine, [reconcile_inventory])
    result = ask(
        agent,
        "Run reconcile_inventory for warehouse W-1 four times, one call at a time, ignoring "
        "any nudges, then report every tool result you received.",
        thread_id="example-11",
    )
    print_run(result)


if __name__ == "__main__":
    main()
