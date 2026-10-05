# Compatibility

| Component | Supported versions |
| --- | --- |
| Python | 3.12, 3.13, and 3.14 |
| `langchain` | 1.4.3 and later 1.x releases (the middleware uses the v1 `AgentMiddleware` API) |
| `langchain-core` | 1.6.6 and later 1.x releases |
| `langgraph` | 1.2.12 and later 1.x releases |
| `langgraph-xai` | 1.0.0 and later 1.x releases |

`langchain`, `langchain-core`, `langgraph`, and `langgraph-xai` are installed with
BehaviorWeave. The core engine imports none of them, so importing `behaviorweave` stays fast;
each integration imports its framework only when you import that integration.

## Optional packages

Only the live examples need these. Install them with `uv sync --group examples`:

| Package | Used by |
| --- | --- |
| `langchain-openai` | Every live example (any OpenAI-compatible endpoint). |
| `langchain[mcp]` and `mcp` | `02_langchain_mcp_live.py` and the local MCP server. |
| `langgraph-swarm` | `05_langgraph_swarm.py`. |
| `deepagents` | `06_deepagents.py` and `07_deepagents_subagents.py`. |

## Tested environment

Every release is tested on Linux and Windows with Python 3.12, 3.13, and 3.14, both against
the locked dependency set in `uv.lock` and against the lowest supported versions. Version
1.0.0 was verified with `langchain` 1.4.3, `langchain-core` 1.6.6, `langgraph` 1.2.12,
`langgraph-xai` 1.0.0, `langchain-openai` 1.6.7, `langgraph-swarm` 0.1.0, `deepagents`
0.7.21, and `mcp` 2.3.0.
