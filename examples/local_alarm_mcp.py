"""A real stdio MCPServer used by the live MCP example.

This server exposes operational tools over Model Context Protocol. It is intentionally
local and deterministic so no third-party MCP endpoint or additional credentials are
needed. BehaviorWeave runs in the server process at the actual MCP tool boundary.
"""

from mcp.server.mcpserver import MCPServer

from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule

mcp = MCPServer("behaviorweave-local-operations")
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "mcp-repeat-nudge",
            "repeated_tool_call",
            2,
            InterventionType.NUDGE,
            message="Reuse this MCP result instead of requesting the same alarm again.",
        ),
        PolicyRule(
            "mcp-repeat-synthesize",
            "repeated_tool_call",
            3,
            InterventionType.FORCE_SYNTHESIS,
            message="Stop repeated MCP calls and synthesize the evidence already received.",
        ),
    ]
)


def observe(tool_name: str, arguments: dict[str, object]) -> str | None:
    decision = engine.process(
        BehaviorEvent.tool_call(tool_name, arguments, scope="local-mcp-session")
    )
    if decision.intervention.kind is InterventionType.NOOP:
        return None
    return (
        f"BehaviorWeave intervention={decision.intervention.kind.value}; "
        f"guidance={decision.intervention.message or decision.intervention.reason}"
    )


@mcp.tool()
def get_alarm(machine: str) -> str:
    """Retrieve observable alarm status for an etching machine."""
    intervention = observe("get_alarm", {"machine": machine})
    result = f"{machine}: chamber-pressure warning; severity=medium; current_status=active."
    return f"{result}\n{intervention}" if intervention else result


@mcp.tool()
def search_incident_history(machine: str) -> str:
    """Retrieve deterministic prior incident evidence for an etching machine."""
    intervention = observe("search_incident_history", {"machine": machine})
    result = f"{machine}: two pressure-drift incidents in the last 30 days."
    return f"{result}\n{intervention}" if intervention else result


if __name__ == "__main__":
    mcp.run()
