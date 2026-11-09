"""Decision metrics through OpenTelemetry."""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionType,
    Outcome,
    PolicyConfigurationError,
    PolicyRule,
)
from behaviorweave.integrations.opentelemetry import DECISIONS_METRIC, OpenTelemetryMetricsSink
from support import at


def _points(reader: InMemoryMetricReader) -> dict[frozenset[tuple[str, object]], int]:
    data = reader.get_metrics_data()
    assert data is not None
    points: dict[frozenset[tuple[str, object]], int] = {}
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            assert scope.scope.name == "behaviorweave"
            for metric in scope.metrics:
                assert (metric.name, metric.unit) == (DECISIONS_METRIC, "{decision}")
                for point in metric.data.data_points:
                    # pyrefly: ignore[missing-attribute]
                    points[frozenset((point.attributes or {}).items())] = point.value
    return points


async def test_decisions_are_counted_with_low_cardinality_attributes() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    engine = BehaviorEngine(
        policies=[PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE)],
        audit_sink=OpenTelemetryMetricsSink(meter_provider=provider),
    )
    events = [
        BehaviorEvent.tool_call("search", scope=f"user-{index % 2}", timestamp=at(index))
        for index in range(4)
    ]
    for event in events:
        await engine.process(event)
    await engine.process(events[-1])
    await engine.process(BehaviorEvent.outcome_event(Outcome.SUCCESS, scope="user-0"))
    await engine.close()

    noop = {
        ("behaviorweave.event.type", "tool_call"),
        ("behaviorweave.intervention", "noop"),
        ("behaviorweave.pattern", "repeated_tool_call"),
        ("behaviorweave.actionable", False),
        ("behaviorweave.suppressed", False),
    }
    nudge = {
        ("behaviorweave.event.type", "tool_call"),
        ("behaviorweave.intervention", "nudge"),
        ("behaviorweave.pattern", "repeated_tool_call"),
        ("behaviorweave.policy", "nudge"),
        ("behaviorweave.actionable", True),
        ("behaviorweave.suppressed", False),
    }
    unobserved = {
        ("behaviorweave.event.type", "outcome"),
        ("behaviorweave.intervention", "noop"),
        ("behaviorweave.actionable", False),
        ("behaviorweave.suppressed", False),
        ("behaviorweave.duplicate", False),
    }
    assert _points(reader) == {
        frozenset({*noop, ("behaviorweave.duplicate", False)}): 2,
        frozenset({*nudge, ("behaviorweave.duplicate", False)}): 2,
        frozenset({*nudge, ("behaviorweave.duplicate", True)}): 1,
        frozenset(unobserved): 1,
    }, "scopes never become attributes"
    provider.shutdown()


async def test_the_global_meter_provider_is_the_default() -> None:
    sink = OpenTelemetryMetricsSink()
    await sink.flush()
    await sink.close()


def test_rejects_a_meter_provider_of_the_wrong_type() -> None:
    with pytest.raises(PolicyConfigurationError, match="not object"):
        # pyrefly: ignore[bad-argument-type]
        OpenTelemetryMetricsSink(meter_provider=object())
