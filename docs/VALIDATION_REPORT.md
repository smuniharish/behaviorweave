# Validation report

Executed in the repository on 2026-09-23:

| Check | Result |
|---|---|
| Python | PASS — uv-managed CPython 3.12.14 |
| uv | PASS — 0.12.15 |
| BehaviorWeave | PASS — 0.1.0 |
| langgraph | PASS — 1.2.12 |
| langchain | PASS — 1.4.2; public `create_agent` signature inspected |
| langgraph-xai | PASS — 0.1.0 |
| langgraph-swarm | NOT TESTED — example extra not installed |
| deepagents | NOT TESTED — example extra not installed |
| pytest | PASS — 7 tests (including local stdio MCP discovery and execution) |
| ruff | PASS |
| black | PASS |
| pyrefly | PASS |
| MkDocs | PASS — strict build |
| ReadTheDocs | NOT TESTED — configuration supplied |
| wheel/sdist | PASS — `uv build` |
| clean install | PASS — wheel built and editable environment imported |
| real provider smoke test | PASS — owner executed provider-backed flagship examples on 2026-09-23 using an environment-local credential; see execution evidence below |
| local stdio MCP discovery/execution | PASS — tool discovery and three guarded calls verified |
| remote MCP/live provider execution | NOT TESTED — requires an endpoint and a credential |

Commands used: `uv lock`, `uv sync --extra dev`, `uv run pytest -q`,
`uv run ruff check .`, `uv run black --check .`, `uv run pyrefly check`,
`uv run mkdocs build --strict`, and `uv build`.

## Provider-backed smoke evidence

The package owner executed the following opt-in examples locally on 2026-09-23. The
credential remained in the owner's environment and was not copied into this report.

| Example | Result |
|---|---|
| `examples/01_langchain_agent.py` | PASS — the live agent returned an alarm result, observed a repeated tool call, and received an instruction to reuse the existing result. |
| `examples/03_langgraph_custom_graph.py` | PASS — the compiled LangGraph workflow returned a structured operational incident report. |
| `examples/04_langgraph_multi_agent.py` | PASS — the live supervisor/specialist workflow returned a preliminary pressure-incident report with containment and investigation actions. |
| `examples/15_complete_agent_guard.py` | PASS — the LangGraph plus `langgraph-xai` guarded-agent workflow returned a pressure warning, historical context, and recommended action. |

Provider-generated prose is not asserted byte-for-byte because model responses are
non-deterministic. The deterministic suite remains the source of behavioral
regression assertions.
