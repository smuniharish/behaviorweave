# Compatibility

| Component | Supported range |
| --- | --- |
| Python | 3.12 through 3.15 |
| LangChain | >=1.4.9,<2 |
| langchain-core | >=1.7.6,<2 |
| LangGraph | >=1.2.20,<2 |
| agxai | >=1.0.2,<2 |

These are installed with BehaviorWeave. Framework imports happen only in integrations,
so importing the core does not import the frameworks.

## Downstream packages

| Package | Role and customization |
| --- | --- |
| agxai | Runtime configuration, registry, store, exporters, plugins, attribution, explanation, capture and disclosure policies; see [inventory](agxai.md#customization). |
| LangChain / langchain-core | Application owns model, tools, agent, checkpointing, and middleware composition. |
| LangGraph | Application owns routing, graph configuration, checkpointer, and BaseStore. |
| deepagents | Example agent factory; pass BehaviorWeave through its middleware options. |
| langgraph-swarm | Example handoffs; host reports transitions through the event adapter. |
| langchain-openai | Example model; host configures model and OpenAI-compatible endpoint. |
| mcp | Example server and transport; host chooses session scope/authentication. |
| psycopg / psycopg-pool | PostgreSQL reference storage; inject a configured pool or use `connect`. |
| redis | Redis reference storage; inject a configured async client or use `connect`. |
| langgraph-checkpoint-postgres | Example LangGraph store; host owns connection and setup. |
| OpenTelemetry SDK/exporter | Application supplies provider, processor, exporter, resource, and TLS/auth settings. |

Development tools and framework implementation dependencies are not runtime extension
surfaces. Install `uv sync --all-groups` for the tested repository environment in `uv.lock`.
