"""Guard a Deep Agents agent with BehaviorWeaveMiddleware.

``create_deep_agent`` accepts LangChain agent middleware, so BehaviorWeave observes every tool
call the deep agent makes: the operational tools and its built-in planning and file tools.

Run:
    uv sync --group examples
    uv run python examples/06_deepagents.py
"""

from deepagents import create_deep_agent

from behaviorweave import BehaviorEngine
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware
from common import (
    OPERATIONS_TOOLS,
    SYSTEM_PROMPT,
    ask,
    create_model,
    print_run,
    repeat_guard_policies,
)


def main() -> None:
    engine = BehaviorEngine(policies=repeat_guard_policies())
    agent = create_deep_agent(
        model=create_model(),
        tools=list(OPERATIONS_TOOLS),
        system_prompt=SYSTEM_PROMPT,
        middleware=[BehaviorWeaveMiddleware(engine)],
    )
    result = ask(
        agent,
        "Investigate the ETCH-3 pressure alarm. Check the alarm twice to confirm it, review "
        "the incident history, and recommend a next action.",
        thread_id="example-06",
    )
    print_run(result)


if __name__ == "__main__":
    main()
