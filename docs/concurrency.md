# Concurrency and persistence

BehaviorWeave preserves atomic behavioral state updates for concurrent threads and
async tasks in a single process. A 100-event concurrent tool-boundary test verifies
that valid events are not lost.

The default runtime is not a distributed coordination service. Applications running
across processes or workers must use a durable state provider with atomic update,
expiry, and idempotency guarantees appropriate to their deployment. Event identifiers
make duplicate delivery deterministic within the configured retention period.
