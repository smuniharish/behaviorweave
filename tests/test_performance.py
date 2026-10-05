"""Generous performance budgets that catch order-of-magnitude regressions."""

import time
import tracemalloc

import pytest

from behaviorweave import BehaviorEngine, BehaviorEvent, InterventionType, PolicyRule

pytestmark = pytest.mark.benchmark


def _engine() -> BehaviorEngine:
    return BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 3, InterventionType.NUDGE),
            PolicyRule("stop", "repeated_tool_call", 6, InterventionType.STOP),
        ]
    )


def test_engine_throughput_stays_within_budget() -> None:
    engine = _engine()
    events = [
        BehaviorEvent.tool_call("get_alarm", {"machine": f"ETCH-{i % 3}"}, scope=f"t-{i % 100}")
        for i in range(20_000)
    ]

    started = time.perf_counter()
    for event in events:
        engine.process(event)

    # About 0.25 seconds on a laptop; the budget leaves room for slow shared runners.
    assert time.perf_counter() - started < 10.0


def test_memory_stays_bounded_when_arguments_never_repeat() -> None:
    engine = _engine()
    events = [
        BehaviorEvent.tool_call("search", {"query": f"q-{i}", "page": i}, scope="thread-1")
        for i in range(5_000)
    ]

    tracemalloc.start()
    for event in events:
        engine.process(event)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(engine.store._states) == 1  # type: ignore[attr-defined]
    assert peak < 5_000_000
