"""Live multi-agent execution with guarded delegation and real LangChain subagents.

Each delegate tool invokes an independently constructed LangChain v1 agent. The
supervisor itself is also a LangChain agent. BehaviorWeave observes calls at each
delegation boundary and returns intervention guidance on repeated delegation.
"""

from __future__ import annotations

from typing import Any

from common import create_explabs_model, create_langchain_agent
from langchain.tools import tool

from behaviorweave import BehaviorEngine, BehaviorEvent, EventType, InterventionType, PolicyRule


def delegation_guard(engine: BehaviorEngine, scope: str, target: str) -> str | None:
    decision = engine.process(
        BehaviorEvent(
            EventType.DELEGATION,
            scope=scope,
            agent_name="supervisor",
            target_agent=target,
        )
    )
    if decision.intervention.kind is InterventionType.NOOP:
        return None
    return f"BehaviorWeave={decision.intervention.kind.value}: {decision.intervention.message}"


def specialist(name: str, role: str, question: str) -> str:
    agent = create_langchain_agent(create_explabs_model(), [])
    result: dict[str, Any] = agent.invoke(
        {"messages": [{"role": "user", "content": f"You are {name}, {role}. {question}"}]}
    )
    return str(result["messages"][-1].content)


def main() -> None:
    scope = "live-multi-agent-run"
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "repeated-delegation",
                "delegation_streak",
                2,
                InterventionType.WARNING,
                message="The same specialist was delegated repeatedly; use its existing finding.",
            ),
            PolicyRule(
                "delegation-stop",
                "delegation_streak",
                3,
                InterventionType.FORCE_SYNTHESIS,
                message="Stop delegating and synthesize the specialist findings.",
            ),
        ]
    )

    @tool
    def ask_researcher(question: str) -> str:
        """Delegate evidence gathering to the researcher."""
        guard = delegation_guard(engine, scope, "researcher")
        if guard:
            return guard
        return specialist("researcher", "an incident evidence specialist", question)

    @tool
    def ask_analyst(question: str) -> str:
        """Delegate evidence analysis to the analyst."""
        guard = delegation_guard(engine, scope, "analyst")
        if guard:
            return guard
        return specialist("analyst", "a root-cause analysis specialist", question)

    @tool
    def ask_writer(question: str) -> str:
        """Delegate final communication planning to the writer."""
        guard = delegation_guard(engine, scope, "writer")
        if guard:
            return guard
        return specialist("writer", "an operations communication specialist", question)

    supervisor = create_langchain_agent(
        create_explabs_model(), [ask_researcher, ask_analyst, ask_writer]
    )
    result = supervisor.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Coordinate a concise ETCH-3 pressure incident report. Delegate once to "
                        "researcher, once to analyst, and once to writer. Do not repeat delegation "
                        "after a BehaviorWeave warning; synthesize the available findings."
                    ),
                }
            ]
        }
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
