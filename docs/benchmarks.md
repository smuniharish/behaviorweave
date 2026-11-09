# Benchmarks

```bash
uv run python scripts/benchmark.py --events 20000 --repeats 5
```

The command reports median async engine throughput, stored-state count, and traced peak
memory as JSON. It measures a repeated-tool-call policy ladder, not model latency.

A local Windows/Python 3.14 run with 5,000 events and three repeats measured about 115,000
events/second and 0.02 MB traced peak memory for the unique-argument stream. This is a
machine-specific observation, not an SLA. Run it on your deployment hardware and backend.

Consecutive patterns use one history per scope; frequency patterns use one per identity.
Use expiry and scope cleanup where identity cardinality is unbounded.
