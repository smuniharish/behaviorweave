# Changelog

## [1.1.0]

- Async engine processing, storage, patterns, audit sinks, and lifecycle.
- ABC extension contracts for custom state stores, patterns, and audit sinks.
- agxai integration with every runtime setting and capability injectable.
- `AgxaiAuditSink` records intervention evidence and decisions in the active run.
- `BehaviorWeaveObservability` evaluates captured events while preserving the exporter.
- `LangGraphBehaviorStateStore` reuses a host application's BaseStore and namespace.
- Middleware halts persist in the engine's state store; decision hooks may be async.
- Serializable intervention decisions and reusable store/pattern conformance tests.
- Nineteen async examples, including PostgreSQL, Redis, and OpenTelemetry.
- Zensical documentation, integration and extension Agent Skills, pyrefly, uv packaging,
  Python 3.12-3.15 validation, and 100% source branch coverage.

## [1.0.0]

- Deterministic behavioral policies, LangChain middleware, scope isolation, idempotent
  event delivery, concurrency tests, and executable documentation.

## [0.1.0]

- Initial behavioral pattern and intervention engine.
