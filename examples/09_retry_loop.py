"""Cap a host-side retry loop with BehaviorWeave retry signals.

``charge_card`` retries an unreliable payment provider internally. Each retry is reported
with ``LangChainEventAdapter.retry``; when the retry streak reaches three, the tool stops
retrying and returns the policy guidance to the agent instead of hammering the provider.

Run:
    uv sync --group examples
    uv run python examples/09_retry_loop.py
"""

from langchain.tools import tool

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import LangChainEventAdapter, default_guidance
from common import ask, guarded_agent, print_run

engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "retry-cap",
            "retry_streak",
            3,
            InterventionType.STOP,
            message="The payment provider is unavailable. Do not retry; tell the customer.",
        )
    ]
)
adapter = LangChainEventAdapter()


def call_payment_provider(order_id: str) -> str:
    raise TimeoutError(f"payment provider timed out for {order_id}")


@tool
def charge_card(order_id: str) -> str:
    """Charge the card on file for one order, retrying transient provider failures."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return call_payment_provider(order_id)
        except TimeoutError as error:
            decision = engine.process(adapter.retry(scope=order_id, tool_name="charge_card"))
            print(f"attempt {attempt} failed: {error}")
            if decision.intervention.kind.is_terminal:
                return default_guidance(decision)


def main() -> None:
    agent = guarded_agent(engine, [charge_card])
    result = ask(agent, "Charge the card for order ORD-7.", thread_id="example-09")
    print_run(result)


if __name__ == "__main__":
    main()
