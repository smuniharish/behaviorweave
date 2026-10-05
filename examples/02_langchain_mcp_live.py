"""Use BehaviorWeave inside an MCP server, with tools discovered by a LangChain agent.

The agent discovers the tools of ``local_alarm_mcp.py`` through LangChain's MCP adapter. The
server evaluates BehaviorWeave at its own tool boundary, so every MCP client is guarded.

Run:
    uv sync --group examples
    uv run python examples/02_langchain_mcp_live.py

Set ``BEHAVIORWEAVE_MCP_URL`` to an ``https://.../mcp`` endpoint to use a remote server instead.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from langchain.agents import create_agent
from langchain.mcp import MCPAdapter

from common import SYSTEM_PROMPT, create_model, print_run


async def main() -> None:
    server = os.environ.get("BEHAVIORWEAVE_MCP_URL") or Path(__file__).with_name(
        "local_alarm_mcp.py"
    )
    async with MCPAdapter(server) as adapter:
        tools = await adapter.list_tools()
        agent = create_agent(create_model(), tools, system_prompt=SYSTEM_PROMPT)
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Call get_alarm for ETCH-3 three times, one call at a time, "
                            "then summarize the alarm."
                        ),
                    }
                ]
            }
        )
    print_run(result)


if __name__ == "__main__":
    asyncio.run(main())
