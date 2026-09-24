"""100 concurrent real provider-backed LangChain agent runs against one guard.

Each worker constructs and invokes a LangChain v1 agent using the configured live
OpenAI-compatible model. All agents share one BehaviorWeave guard, so this is both a
real API load test and an atomic shared-state test. It can incur provider cost.

Run:
    uv sync --extra real-model
    $env:EXPLABS_API_KEY = "<credential>"
    uv run python examples/14_concurrency.py
"""

import os
from concurrent.futures import ThreadPoolExecutor

from common import default_guard, invoke_live_agent


def main() -> None:
    if not os.environ.get("EXPLABS_API_KEY"):
        raise SystemExit(
            "EXPLABS_API_KEY is required because this example runs real provider-backed agents."
        )

    calls = int(os.environ.get("BEHAVIORWEAVE_CONCURRENCY_CALLS", "100"))
    guard = default_guard(scope="concurrent-live-agent-run")

    def invoke_worker(index: int) -> str:
        result = invoke_live_agent(
            (
                "Call get_alarm exactly once for ETCH-3, include the returned evidence in "
                f"your concise report, and label this request worker-{index}."
            ),
            guard=guard,
        )
        return str(result["messages"][-1].content)

    with ThreadPoolExecutor(max_workers=min(20, calls)) as pool:
        responses = list(pool.map(invoke_worker, range(calls)))

    state = guard.engine.store.get("concurrent-live-agent-run:repeated_tool_call")
    print(
        f"Completed {len(responses)} real model-backed LangChain agent runs; "
        f"observed tool-repeat count={state.count if state else 0}."
    )


if __name__ == "__main__":
    main()
