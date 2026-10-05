"""A local stdio MCP server whose tools are guarded by BehaviorWeave.

Used by ``02_langchain_mcp_live.py`` and the MCP integration test. It needs no credentials.
BehaviorWeave runs in the server process at the MCP tool boundary, so every client that
calls these tools receives the same deterministic guidance.

Run standalone:
    uv run python examples/local_alarm_mcp.py
"""

from mcp.server.mcpserver import MCPServer

from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import default_guidance

mcp = MCPServer("behaviorweave-local-operations")
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "mcp-repeat-nudge",
            "repeated_tool_call",
            2,
            InterventionType.NUDGE,
            message="Reuse this result instead of requesting the same alarm again.",
        ),
        PolicyRule(
            "mcp-repeat-synthesize",
            "repeated_tool_call",
            3,
            InterventionType.FORCE_SYNTHESIS,
            message="Stop repeating this call and synthesize the evidence already received.",
        ),
    ]
)


def guidance(tool_name: str, arguments: dict[str, object]) -> str | None:
    """Evaluate one MCP tool call and return guidance text for actionable decisions."""
    decision = engine.process(
        BehaviorEvent.tool_call(tool_name, arguments, scope="local-mcp-session")
    )
    return default_guidance(decision) if decision.actionable else None


@mcp.tool()
def get_alarm(machine: str) -> str:
    """Retrieve the current alarm status for an etching machine."""
    note = guidance("get_alarm", {"machine": machine})
    result = f"{machine}: chamber-pressure warning; severity=medium; status=active."
    return f"{result}\n{note}" if note else result


@mcp.tool()
def search_incident_history(machine: str) -> str:
    """Retrieve prior incident evidence for an etching machine."""
    note = guidance("search_incident_history", {"machine": machine})
    result = f"{machine}: two pressure-drift incidents in the last 30 days."
    return f"{result}\n{note}" if note else result


if __name__ == "__main__":
    mcp.run()
