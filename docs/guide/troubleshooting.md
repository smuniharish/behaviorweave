# Troubleshooting

| Symptom | Check |
| --- | --- |
| Engine rejects a custom component | Subclass the appropriate ABC and implement all abstract methods. |
| Counts leak between conversations | Use a separate scope/thread ID for each conversation. |
| No tool intervention | Check pattern ID, threshold, scope, and `block_on`; only configured kinds block. |
| Stream ended without a failure streak | Cancellation and interruption are not failure outcomes. |
| Resumed tool still blocked | Inspect `await middleware.halted(scope)` and explicitly `await middleware.release(scope)`. |
| Unexpected duplicate | Event IDs identify delivery, not argument identity; use a new ID for a new event. |
| State lost on restart | Use durable storage rather than the in-memory default. |
| Replicas lose increments | Use cross-process atomic updates, not the LangGraph adapter's instance-local locks. |
| psycopg fails on Windows | Run on `asyncio.SelectorEventLoop`; the examples' `common.run` configures it. |
| Podman connection hangs on localhost | Try `127.0.0.1` and check published ports and container health. |
| No exported spans | Check OTLP/HTTP port/path, exporter dependencies, and `await runtime.close()`. |

Backend, audit, and hook failures propagate; do not replace them with success-shaped defaults.
See [failure strategy](../architecture/failure-strategy.md) and [security](../security.md).
