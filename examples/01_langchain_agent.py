"""Live LangChain v1 agent: real model + actual guarded tool calls.

Run only after configuring a local process environment:
    uv sync --extra real-model
    $env:EXPLABS_API_KEY = "<credential>"
    uv run python examples/01_langchain_agent.py
"""

from common import invoke_live_agent

if __name__ == "__main__":
    result = invoke_live_agent(
        "Inspect ETCH-3. Call get_alarm for ETCH-3, then deliberately call it twice more. "
        "After any BehaviorWeave intervention, stop repeating calls and summarize the evidence."
    )
    print(result["messages"][-1].content)
