"""Live LangChain v1 agent with tools discovered through a real stdio MCP server.

Run:
    uv sync --extra mcp --extra real-model
    $env:EXPLABS_API_KEY = "<credential>"
    uv run python examples/02_langchain_mcp_live.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from common import create_explabs_model, create_langchain_agent
from langchain.mcp import MCPAdapter


async def main() -> None:
    server = os.environ.get("BEHAVIORWEAVE_MCP_URL") or Path(__file__).with_name(
        "local_alarm_mcp.py"
    )
    async with MCPAdapter(server) as adapter:
        mcp_tools = await adapter.list_tools()
        agent = create_langchain_agent(create_explabs_model(), mcp_tools)
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Investigate ETCH-3 through the available MCP tools. Call get_alarm "
                            "for ETCH-3, then call it twice more. When BehaviorWeave intervenes, "
                            "stop repeating the call and synthesize the result."
                        ),
                    }
                ]
            }
        )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
