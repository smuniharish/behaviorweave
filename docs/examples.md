# Live examples

The [`examples/`](https://github.com/smuniharish/behaviorweave/tree/master/examples)
directory contains fifteen single-file examples. Each drives a **real, provider-backed chat
model** and applies BehaviorWeave at a real runtime boundary. Model wording varies between
runs; BehaviorWeave's guidance lines (`[BehaviorWeave:<kind>] ...`) are deterministic.

## Configure a model

The examples work with any OpenAI-compatible endpoint. Credentials are read only from
environment variables and are never written anywhere.

| Variable | Required | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | yes | API key for the endpoint. |
| `BEHAVIORWEAVE_MODEL` | yes | Chat model name served by the endpoint. |
| `OPENAI_BASE_URL` | no | Endpoint URL; omit to use api.openai.com. |

=== "PowerShell"

    ```powershell
    git clone https://github.com/smuniharish/behaviorweave
    cd behaviorweave
    uv sync --group examples
    $env:OPENAI_API_KEY = "<your-api-key>"
    $env:BEHAVIORWEAVE_MODEL = "<chat-model-name>"
    uv run python examples/01_langchain_agent.py
    ```

=== "bash"

    ```bash
    git clone https://github.com/smuniharish/behaviorweave
    cd behaviorweave
    uv sync --group examples
    export OPENAI_API_KEY="<your-api-key>"
    export BEHAVIORWEAVE_MODEL="<chat-model-name>"
    uv run python examples/01_langchain_agent.py
    ```

!!! info "Cost"
    Every example makes paid provider calls. `14_concurrency.py` runs one agent per worker,
    10 by default; set `BEHAVIORWEAVE_CONCURRENCY_CALLS` to change the load.

!!! note "Endpoint compatibility"
    LangGraph Swarm and Deep Agents label assistant messages with the agent's name, which
    some OpenAI-compatible endpoints reject. The multi-agent examples therefore add
    `OmitMessageNames`, a small model-call middleware in `examples/common.py`.

## Catalog

| Example | Integration | What it shows |
| --- | --- | --- |
| `01_langchain_agent.py` | LangChain middleware | Nudge on a repeated tool call, block the next one. |
| `02_langchain_mcp_live.py` | MCP | BehaviorWeave inside an MCP server discovered by a LangChain agent. |
| `03_langgraph_custom_graph.py` | LangGraph | Bound a write/review loop with a node-execution budget. |
| `04_langgraph_multi_agent.py` | Multi-agent | Warn on repeated delegation before a costly specialist run. |
| `05_langgraph_swarm.py` | LangGraph Swarm | Stop agents that keep handing control back and forth. |
| `06_deepagents.py` | Deep Agents | Guard every tool call of a deep agent. |
| `07_deepagents_subagents.py` | Deep Agents | Separate guards and scopes for a lead agent and its subagent. |
| `08_failure_streak.py` | LangChain middleware | Escalate after consecutive tool failures. |
| `09_retry_loop.py` | LangChain adapter | Cap a host-side retry loop. |
| `10_oscillation.py` | LangGraph adapter | Detect and stop back-and-forth transfers. |
| `11_cooldown.py` | LangChain middleware | Cool down a nudge without muting escalation. |
| `12_policy_escalation.py` | LangChain middleware | Nudge, warn, request human review, then stop. |
| `13_multi_scope.py` | LangChain middleware | Isolate behavioral history per conversation. |
| `14_concurrency.py` | LangChain middleware | One engine shared safely by concurrent agent runs. |
| `15_complete_agent_guard.py` | LangGraph + langgraph-xai | Guarded agent, provenance capture, and a provenance-linked audit. |

## What a run looks like

`01_langchain_agent.py` asks the agent to fetch the same alarm three times. The transcript
shows each tool call and result:

```text
-> get_alarm({'machine': 'ETCH-3'})
   Alarm for ETCH-3: chamber-pressure warning; severity=medium.
-> get_alarm({'machine': 'ETCH-3'})
   Alarm for ETCH-3: chamber-pressure warning; severity=medium.
   [BehaviorWeave:nudge] You already have this result. Reuse it instead of calling the tool again.
-> get_alarm({'machine': 'ETCH-3'})
   [BehaviorWeave:stop] Identical call blocked. Answer with the evidence you already have.

Final answer:
ETCH-3 reports a medium-severity chamber-pressure warning.
```

A model that follows the nudge stops after the second call, so the third call, and the
block, may never happen. Either way, the guidance is identical on every run.

## Reproducible verification

The test suite runs every example on each change without a provider: a rule-based chat model
stands in for the endpoint, and the tests check the BehaviorWeave guidance each example
prints. Runs against a real endpoint are opt-in, because they make paid calls: set
`BEHAVIORWEAVE_LIVE_TESTS=1` together with the variables above, then run
`uv run pytest -m live`.
