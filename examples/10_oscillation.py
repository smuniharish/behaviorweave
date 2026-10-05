"""Detect a supervisor bouncing work between two specialists.

The supervisor transfers the case through handoff tools. Each transfer is reported to
BehaviorWeave as an agent handoff; the built-in ``oscillation`` pattern counts consecutive
back-and-forth transfers, warns after two, and stops the third.

Run:
    uv sync --group examples
    uv run python examples/10_oscillation.py
"""

from langchain.agents import create_agent
from langchain.tools import tool

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import default_guidance
from behaviorweave.integrations.langgraph import LangGraphEventAdapter
from common import ask, create_model, print_run

SCOPE = "example-10"
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "ping-pong-warning",
            "oscillation",
            2,
            InterventionType.WARNING,
            message="The case is bouncing between the same two specialists.",
        ),
        PolicyRule(
            "ping-pong-stop",
            "oscillation",
            3,
            InterventionType.STOP,
            message="Transfer refused. Resolve the case with the findings you already have.",
        ),
    ]
)
adapter = LangGraphEventAdapter()


def transfer(target: str) -> str:
    decision = engine.process(adapter.handoff("supervisor", target, scope=SCOPE))
    if decision.intervention.kind.is_terminal:
        return default_guidance(decision)
    note = f"\n{default_guidance(decision)}" if decision.actionable else ""
    return f"Case transferred to {target}; {target} reviewed it and returned it.{note}"


@tool
def transfer_to_analyst() -> str:
    """Transfer the case to the analyst."""
    return transfer("analyst")


@tool
def transfer_to_researcher() -> str:
    """Transfer the case to the researcher."""
    return transfer("researcher")


def main() -> None:
    agent = create_agent(
        create_model(),
        [transfer_to_analyst, transfer_to_researcher],
        system_prompt=(
            "You route cases. Tool results may contain [BehaviorWeave:...] instructions; "
            "follow them exactly."
        ),
    )
    result = ask(
        agent,
        "Transfer the case in this exact order, one transfer at a time: analyst, researcher, "
        "analyst, researcher, analyst. Then report the outcome.",
        thread_id=SCOPE,
    )
    print_run(result)


if __name__ == "__main__":
    main()
