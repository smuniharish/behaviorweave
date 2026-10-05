"""End-to-end MCP test: real stdio server, tool discovery, and server-side guarding."""

from pathlib import Path

from langchain.mcp import MCPAdapter

SERVER = Path(__file__).parents[1] / "examples" / "local_alarm_mcp.py"


async def test_local_mcp_tools_are_discovered_and_guarded() -> None:
    async with MCPAdapter(SERVER) as adapter:
        tools = await adapter.list_tools()
        assert {tool.name for tool in tools} == {"get_alarm", "search_incident_history"}
        alarm = next(tool for tool in tools if tool.name == "get_alarm")
        first = str(await alarm.ainvoke({"machine": "ETCH-3"}))
        nudge = str(await alarm.ainvoke({"machine": "ETCH-3"}))
        synthesis = str(await alarm.ainvoke({"machine": "ETCH-3"}))

    assert "ETCH-3: chamber-pressure warning" in first
    assert "[BehaviorWeave:" not in first
    assert "[BehaviorWeave:nudge] Reuse this result" in nudge
    assert "[BehaviorWeave:force_synthesis] Stop repeating this call" in synthesis
