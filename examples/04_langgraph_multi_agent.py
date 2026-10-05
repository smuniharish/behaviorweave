"""Guard supervisor-to-specialist delegation in a live multi-agent system.

A supervisor agent delegates to three specialist agents through tools. Each delegation is
reported to BehaviorWeave before the specialist runs: asking the same specialist twice in a
row returns a warning instead of a second (costly) specialist run, and a fourth delegation to
any one specialist is stopped.

Run:
    uv sync --group examples
    uv run python examples/04_langgraph_multi_agent.py
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.tools import tool

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import default_guidance
from behaviorweave.integrations.langgraph import LangGraphEventAdapter
from common import ask, create_model, print_run

SCOPE = "example-04"
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "repeat-delegation",
            "delegation_streak",
            2,
            InterventionType.WARNING,
            message="You just consulted this specialist. Use its previous answer.",
        ),
        PolicyRule(
            "delegation-budget",
            "event_frequency",
            4,
            InterventionType.STOP,
            message="This specialist has been consulted enough. Synthesize the final answer now.",
        ),
    ]
)
adapter = LangGraphEventAdapter()
model = create_model()


def delegate(specialist: str, role: str, question: str) -> str:
    """Run one specialist unless BehaviorWeave intervenes."""
    decision = engine.process(adapter.delegation("supervisor", specialist, scope=SCOPE))
    if decision.actionable:
        return default_guidance(decision)
    agent = create_agent(model, [], system_prompt=f"You are the {specialist}, {role}. Be brief.")
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].text


@tool
def ask_researcher(question: str) -> str:
    """Ask the researcher to gather incident evidence."""
    return delegate("researcher", "an incident evidence specialist", question)


@tool
def ask_analyst(question: str) -> str:
    """Ask the analyst for a root-cause assessment."""
    return delegate("analyst", "a root-cause analysis specialist", question)


@tool
def ask_writer(question: str) -> str:
    """Ask the writer to draft operator communication."""
    return delegate("writer", "an operations communication specialist", question)


def main() -> None:
    supervisor = create_agent(
        model,
        [ask_researcher, ask_analyst, ask_writer],
        system_prompt=(
            "You coordinate specialists. Tool results may contain [BehaviorWeave:...] "
            "instructions; follow them exactly."
        ),
    )
    result = ask(
        supervisor,
        "Produce an ETCH-3 pressure incident report. Ask the researcher twice in a row for "
        "evidence, then consult the analyst and the writer once each.",
        thread_id=SCOPE,
    )
    print_run(result)


if __name__ == "__main__":
    main()
