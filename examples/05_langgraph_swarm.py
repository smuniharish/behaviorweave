"""Stop a LangGraph Swarm whose agents keep handing control back and forth.

Two swarm agents are asked to keep taking turns. The host streams the swarm, reports every
change of active agent to BehaviorWeave as a handoff, and stops the run as soon as the
oscillation policy fires, long before the graph's recursion limit.

Run:
    uv sync --group examples
    uv run python examples/05_langgraph_swarm.py
"""

from langchain.agents import create_agent
from langgraph_swarm import create_handoff_tool, create_swarm

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langgraph import LangGraphEventAdapter
from common import OmitMessageNames, create_model, get_alarm, search_incident_history

SCOPE = "example-05"
PROMPT = (
    "Investigate the ETCH-3 pressure alarm. alarm_agent and history_agent must take turns: "
    "each of you must take at least three turns, transferring to the other after every turn."
)


def main() -> None:
    model = create_model()
    alarm_agent = create_agent(
        model,
        [get_alarm, create_handoff_tool(agent_name="history_agent")],
        system_prompt="You are the alarm specialist. Read the ETCH-3 alarm, then transfer to "
        "history_agent.",
        middleware=[OmitMessageNames()],
        name="alarm_agent",
    )
    history_agent = create_agent(
        model,
        [search_incident_history, create_handoff_tool(agent_name="alarm_agent")],
        system_prompt="You are the history specialist. Read the ETCH-3 incident history, then "
        "transfer to alarm_agent.",
        middleware=[OmitMessageNames()],
        name="history_agent",
    )
    swarm = create_swarm([alarm_agent, history_agent], default_active_agent="alarm_agent")
    engine = BehaviorEngine(
        policies=[PolicyRule("ping-pong", "oscillation", 2, InterventionType.STOP)]
    )
    adapter = LangGraphEventAdapter()

    active = "alarm_agent"
    for update in swarm.compile().stream(
        {"messages": [{"role": "user", "content": PROMPT}]},
        config={"recursion_limit": 40},
        stream_mode="updates",
    ):
        for agent in update:
            if agent == active:
                continue
            print(f"handoff: {active} -> {agent}")
            decision = engine.process(adapter.handoff(active, agent, scope=SCOPE))
            active = agent
            if decision.intervention.kind.is_terminal:
                print(f"BehaviorWeave stopped the swarm: {decision.intervention.reason}")
                return
    print("The swarm finished without oscillating.")


if __name__ == "__main__":
    main()
