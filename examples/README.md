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

Every example except `20_batch_replay.py` makes paid provider calls. `14_concurrency.py` runs one agent per worker
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
| [`13_multi_scope.py`](13_multi_scope.py) | LangChain middleware | Isolate behavioral history per conversation, then release it. |
| [`14_concurrency.py`](14_concurrency.py) | LangChain middleware | One engine shared safely by concurrent agent runs. |
| [`15_complete_agent_guard.py`](15_complete_agent_guard.py) | LangGraph + agxai | Guarded agent, semantic audit, and provenance-linked decisions. |
| [`16_postgres_state_store.py`](16_postgres_state_store.py) | PostgreSQL | Two replicas sharing atomic, durable history. |
| [`17_redis_state_store.py`](17_redis_state_store.py) | Redis | Distributed history with WATCH/MULTI updates. |
| [`18_langgraph_store.py`](18_langgraph_store.py) | LangGraph BaseStore | Existing application storage, namespace, and TTL. |
| [`19_agxai_opentelemetry.py`](19_agxai_opentelemetry.py) | agxai + OTel | Captured events, policy audit, decision metrics, and OTLP/HTTP export. |
| [`20_batch_replay.py`](20_batch_replay.py) | Engine | Batch re-evaluation, fan-out audit, idempotent replay, scope release. |

The shared helpers live in [`common.py`](common.py).

## Local services

```powershell
podman run -d --name bw-postgres -p 55432:5432 -e POSTGRES_PASSWORD=postgres docker.io/library/postgres:18-alpine
podman run -d --name bw-redis -p 56379:6379 docker.io/library/redis:8-alpine
$env:BEHAVIORWEAVE_POSTGRES_URL = "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
$env:BEHAVIORWEAVE_REDIS_URL = "redis://127.0.0.1:56379/0"
uv run pytest tests/test_reference_stores.py tests/test_examples.py -m "not live"
```

The database credentials above are for local disposable test services only.
Reference-store contracts truncate their dedicated test table/key prefix: never point them
at production storage. Scripts use unique conversation IDs so repeated runs stay isolated.
On Windows, the database examples use a selector event loop for psycopg.

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to an OTLP/HTTP endpoint, such as
`http://127.0.0.1:4318`, for example 19. Without it, span names and decision counts are
printed. The example exports traces and the `behaviorweave.decisions` metric, so send it to
an OTel Collector, which accepts both. Exporter credentials and TLS
settings use the standard OpenTelemetry environment variables.

For Collector-to-Jaeger forwarding, put both containers on a dedicated network:

```powershell
podman network create bw-net
podman run -d --name bw-jaeger --network bw-net -p 16686:16686 docker.io/jaegertracing/jaeger:2.17.0
$config = (Resolve-Path examples\otel-collector.yaml).Path
podman run -d --name bw-otel --network bw-net -p 4318:4318 -v "${config}:/etc/otelcol/config.yaml:ro" docker.io/otel/opentelemetry-collector:latest
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4318"
uv run python examples/19_agxai_opentelemetry.py
```

Open `http://127.0.0.1:16686`, select `behaviorweave-example`, and inspect the `incident`
trace. The Collector prints the decision counts: `podman logs bw-otel`. Insecure Collector-to-Jaeger transport is for this isolated local network only.
Remove only these named containers when finished.

## Testing

The repository's test suite runs every example offline on each change: a rule-based chat
model stands in for the provider, and the tests check the BehaviorWeave guidance each example
prints. Database examples require the service URLs above and are skipped otherwise.
To run the examples against your endpoint through the test suite as well, set
`BEHAVIORWEAVE_LIVE_TESTS=1` with the variables above and run `uv run pytest -m live`.
