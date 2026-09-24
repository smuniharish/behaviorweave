# Production readiness

| Area | Classification |
|---|---|
| Event/pattern/policy boundaries | Implemented and tested |
| Scope isolation and engine isolation | Implemented and tested |
| In-process concurrency | Implemented and tested |
| Idempotency | Implemented and tested |
| LangGraph-xAI public integration | Implemented; upstream API compatibility validated |
| LangGraph/LangChain adapters | Implemented; local MCP tool execution tested |
| Real provider execution | Flagship smoke scenarios validated manually; remains credential-dependent and opt-in |
| Durable/distributed persistence | Future |
| Swarm and Deep Agents adapters | Experimental examples |
| Semantic detection | Future |
| Security and privacy guidance | Implemented |
| Package/docs/CI quality gates | Implemented and locally validated |

The alpha release does not claim distributed state safety or stable upstream adapter
contracts. Future roadmap items include Redis/PostgreSQL stores, richer temporal
expressions, and OpenTelemetry hooks.
