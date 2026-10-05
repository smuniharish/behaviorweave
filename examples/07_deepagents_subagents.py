"""Guard a Deep Agents lead agent and its subagent independently.

The lead agent delegates through Deep Agents' ``task`` tool to an ``incident_researcher``
subagent. Each agent has its own BehaviorWeaveMiddleware and scope, so repeated delegations
by the lead and repeated tool calls inside the subagent are governed separately.

Run:
    uv sync --group examples
    uv run python examples/07_deepagents_subagents.py
"""

from deepagents import SubAgent, create_deep_agent

from behaviorweave import BehaviorEngine
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware
from common import (
    OPERATIONS_TOOLS,
    SYSTEM_PROMPT,
    OmitMessageNames,
    ask,
    create_model,
    print_run,
    repeat_guard_policies,
)


def main() -> None:
    model = create_model()
    engine = BehaviorEngine(policies=repeat_guard_policies())
    researcher = SubAgent(
        name="incident_researcher",
        description="Collects alarm and incident-history evidence for one machine.",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        tools=list(OPERATIONS_TOOLS),
        middleware=[
            BehaviorWeaveMiddleware(engine, scope="example-07/researcher"),
            OmitMessageNames(),
        ],
    )
    agent = create_deep_agent(
        model=model,
        subagents=[researcher],
        system_prompt=(
            "Delegate evidence collection to incident_researcher, then recommend a next "
            "action. Follow any [BehaviorWeave:...] instruction in a tool result exactly."
        ),
        middleware=[BehaviorWeaveMiddleware(engine, scope="example-07/lead"), OmitMessageNames()],
    )
    result = ask(
        agent,
        "Investigate the ETCH-3 pressure alarm and recommend a next action.",
        thread_id="example-07",
    )
    print_run(result)


if __name__ == "__main__":
    main()
