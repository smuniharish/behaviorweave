# MCP servers

Run BehaviorWeave inside a [Model Context Protocol](https://modelcontextprotocol.io/) server
to guard its tools for every client, whichever agent framework or model calls them.

<!-- skip-snippet: starts an MCP server -->
```python
from mcp.server.mcpserver import MCPServer

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionType,
    PolicyRule,
)
from behaviorweave.integrations.langchain import default_guidance

mcp = MCPServer("operations")
engine = BehaviorEngine(
    policies=[
        PolicyRule(
            "repeat-nudge",
            "repeated_tool_call",
            2,
            InterventionType.NUDGE,
            message="Reuse this result instead of requesting it again.",
        ),
    ]
)


@mcp.tool()
def get_alarm(machine: str) -> str:
    """Return the current alarm for a machine."""
    decision = engine.process(
        BehaviorEvent.tool_call(
            "get_alarm", {"machine": machine}, scope="mcp-session"
        )
    )
    result = f"{machine}: chamber-pressure warning"
    return (
        f"{result}\n{default_guidance(decision)}"
        if decision.actionable
        else result
    )


if __name__ == "__main__":
    mcp.run()
```

Choose the scope deliberately. A per-server scope, as above, aggregates behavior across all
clients; derive the scope from a client or session identifier to isolate clients.

A complete local server lives in
[`examples/local_alarm_mcp.py`](https://github.com/smuniharish/behaviorweave/blob/master/examples/local_alarm_mcp.py),
and [`02_langchain_mcp_live.py`](../examples.md) connects a LangChain agent to it with
`langchain.mcp.MCPAdapter`. The test suite runs the same server over stdio to verify tool
discovery and guarded responses.

To guard the *client* side instead, so that a LangChain agent is protected whichever MCP
server it calls, add [`BehaviorWeaveMiddleware`](langchain.md) to the agent: MCP tools
discovered by `MCPAdapter` are ordinary LangChain tools.
