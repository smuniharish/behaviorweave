# BehaviorWeave examples

Each example is a single runnable file that drives a **real, provider-backed chat model**
through LangChain or LangGraph and applies BehaviorWeave at a real runtime boundary. Model
wording varies between runs; the BehaviorWeave guidance lines (`[BehaviorWeave:<kind>] ...`)
are deterministic.

## Setup

Install the example dependencies and configure any OpenAI-compatible endpoint through the
environment. Credentials are read only from environment variables.

PowerShell:

```powershell
uv sync --group examples
$env:OPENAI_API_KEY = "<your-api-key>"
$env:BEHAVIORWEAVE_MODEL = "<chat-model-name>"
$env:OPENAI_BASE_URL = "https://your-endpoint.example/v1"  # optional
uv run python examples/01_langchain_agent.py
```

bash:

```bash
uv sync --group examples
export OPENAI_API_KEY="<your-api-key>"
export BEHAVIORWEAVE_MODEL="<chat-model-name>"
export OPENAI_BASE_URL="https://your-endpoint.example/v1"  # optional
uv run python examples/01_langchain_agent.py
```

Every example makes paid provider calls. `14_concurrency.py` runs one agent per worker
(10 by default; set `BEHAVIORWEAVE_CONCURRENCY_CALLS` to change it).

LangGraph Swarm and Deep Agents label assistant messages with the agent's name, which some
OpenAI-compatible endpoints reject; the multi-agent examples add `OmitMessageNames` from
[`common.py`](common.py) for compatibility.

## Catalog

| Example | Integration | What it shows |
| --- | --- | --- |
| [`01_langchain_agent.py`](01_langchain_agent.py) | LangChain middleware | Nudge on a repeated tool call, block the next one. |
| [`02_langchain_mcp_live.py`](02_langchain_mcp_live.py) | MCP | BehaviorWeave inside an MCP server ([`local_alarm_mcp.py`](local_alarm_mcp.py)). |
| [`03_langgraph_custom_graph.py`](03_langgraph_custom_graph.py) | LangGraph | Bound a write/review loop with a node-execution budget. |
| [`04_langgraph_multi_agent.py`](04_langgraph_multi_agent.py) | Multi-agent | Warn on repeated delegation before a costly specialist run. |
| [`05_langgraph_swarm.py`](05_langgraph_swarm.py) | LangGraph Swarm | Stop agents that keep handing control back and forth. |
| [`06_deepagents.py`](06_deepagents.py) | Deep Agents | Guard every tool call of a deep agent. |
| [`07_deepagents_subagents.py`](07_deepagents_subagents.py) | Deep Agents | Separate guards and scopes for a lead agent and its subagent. |
| [`08_failure_streak.py`](08_failure_streak.py) | LangChain middleware | Escalate after consecutive tool failures. |
| [`09_retry_loop.py`](09_retry_loop.py) | LangChain adapter | Cap a host-side retry loop. |
| [`10_oscillation.py`](10_oscillation.py) | LangGraph adapter | Detect and stop back-and-forth transfers. |
| [`11_cooldown.py`](11_cooldown.py) | LangChain middleware | Cool down a nudge without muting escalation. |
| [`12_policy_escalation.py`](12_policy_escalation.py) | LangChain middleware | Nudge, warn, request human review, then stop. |
| [`13_multi_scope.py`](13_multi_scope.py) | LangChain middleware | Isolate behavioral history per conversation. |
| [`14_concurrency.py`](14_concurrency.py) | LangChain middleware | One engine shared safely by concurrent agent runs. |
| [`15_complete_agent_guard.py`](15_complete_agent_guard.py) | LangGraph + langgraph-xai | Guarded agent, provenance capture, and a provenance-linked audit. |

The shared helpers live in [`common.py`](common.py).

## Testing

The repository's test suite runs every example offline on each change: a rule-based chat
model stands in for the provider, and the tests check the BehaviorWeave guidance each example
prints. To run the examples against your endpoint through the test suite as well, set
`BEHAVIORWEAVE_LIVE_TESTS=1` with the variables above and run `uv run pytest -m live`.
