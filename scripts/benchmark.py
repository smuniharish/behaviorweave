"""Measure BehaviorWeave's engine throughput and memory footprint.

Prints one JSON object: the median events per second for a typical two-policy engine
processing tool calls across many scopes, and the stored state count and traced peak memory
after a stream of tool calls whose arguments never repeat.

Usage:
    uv run python scripts/benchmark.py [--events N] [--repeats N]
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
import tracemalloc

from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule


def engine() -> BehaviorEngine:
    """Return the engine under test: a nudge-then-stop ladder on repeated tool calls."""
    return BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 3, InterventionType.NUDGE),
            PolicyRule("stop", "repeated_tool_call", 6, InterventionType.STOP),
        ]
    )


def throughput(events: int, repeats: int) -> float:
    """Return the median events per second over ``repeats`` runs of ``events`` tool calls."""
    stream = [
        BehaviorEvent.tool_call(
            "get_alarm", {"machine": f"ETCH-{i % 3}"}, scope=f"thread-{i % 100}"
        )
        for i in range(events)
    ]
    rates = []
    for _ in range(repeats):
        subject = engine()
        gc.collect()
        started = time.perf_counter()
        for event in stream:
            subject.process(event)
        rates.append(events / (time.perf_counter() - started))
    return statistics.median(rates)


def memory(events: int) -> tuple[int, float]:
    """Return the stored state count and peak traced megabytes for unique-argument calls."""
    subject = engine()
    stream = [
        BehaviorEvent.tool_call("search", {"query": f"q-{i}", "page": i}, scope="thread-1")
        for i in range(events)
    ]
    gc.collect()
    tracemalloc.start()
    for event in stream:
        subject.process(event)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # The in-memory store has no public size API, so count its private table.
    states = len(getattr(subject.store, "_states", {}))
    return states, peak / 1_000_000


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark and print its results as JSON."""
    parser = argparse.ArgumentParser(description="Measure engine throughput and memory.")
    parser.add_argument("--events", type=int, default=20_000, help="events per run")
    parser.add_argument("--repeats", type=int, default=5, help="throughput runs (median)")
    arguments = parser.parse_args(argv)
    states, peak = memory(arguments.events)
    result = {
        "events_per_second": round(throughput(arguments.events, arguments.repeats)),
        "unique_argument_states": states,
        "unique_argument_peak_mb": round(peak, 2),
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
