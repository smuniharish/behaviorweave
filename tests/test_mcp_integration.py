from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_local_mcp_tools_are_discovered_and_guarded():
    from langchain.mcp import MCPAdapter

    server = Path(__file__).parents[1] / "examples" / "local_alarm_mcp.py"
    async with MCPAdapter(server) as adapter:
        tools = await adapter.list_tools()
        assert {tool.name for tool in tools} == {"get_alarm", "search_incident_history"}
        alarm = next(tool for tool in tools if tool.name == "get_alarm")
        await alarm.ainvoke({"machine": "ETCH-3"})
        nudge = await alarm.ainvoke({"machine": "ETCH-3"})
        synthesis = await alarm.ainvoke({"machine": "ETCH-3"})

    assert "intervention=nudge" in str(nudge)
    assert "intervention=force_synthesis" in str(synthesis)
