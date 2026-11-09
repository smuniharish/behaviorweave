# OpenTelemetry

BehaviorWeave exports two OpenTelemetry signals: agxai traces of the guarded execution, and
the engine's own decision metrics.

## Decision metrics

Install the `otel` extra: `pip install "behaviorweave[otel]"`. Pass an
[`OpenTelemetryMetricsSink`](../api/index.md#behaviorweave.integrations.opentelemetry.OpenTelemetryMetricsSink)
as the engine's `audit_sink`. Every decision increments the `behaviorweave.decisions` counter
(unit `{decision}`) with these attributes:

| Attribute | Value |
| --- | --- |
| `behaviorweave.event.type` | The event type, such as `tool_call`. |
| `behaviorweave.intervention` | The intervention kind, such as `noop` or `stop`. |
| `behaviorweave.actionable` | Whether the host must act on the decision. |
| `behaviorweave.suppressed` | Whether a cooldown suppressed the intervention. |
| `behaviorweave.duplicate` | Whether the event was already processed. |
| `behaviorweave.pattern` | The matching pattern, when one observed the event. |
| `behaviorweave.policy` | The policy that fired, when one did. |

Scopes are never attributes: they are unbounded and often identify a user or conversation.
Without a `meter_provider`, the sink uses the global provider, so it records nothing until
the application configures one.

```python
import asyncio

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    InterventionType,
    PolicyRule,
)
from behaviorweave.integrations.opentelemetry import OpenTelemetryMetricsSink


async def main() -> None:
    reader = InMemoryMetricReader()
    sink = OpenTelemetryMetricsSink(
        meter_provider=MeterProvider(metric_readers=[reader])
    )
    rule = PolicyRule("repeat", "repeated_tool_call", 2, InterventionType.STOP)
    async with BehaviorEngine(policies=[rule], audit_sink=sink) as engine:
        for _ in range(2):
            await engine.process(
                BehaviorEvent.tool_call("lookup", scope="conversation-1")
            )
    data = reader.get_metrics_data()
    assert data is not None
    points = (
        data.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points
    )
    print(
        sorted(p.attributes["behaviorweave.intervention"] for p in points)
    )  # ['noop', 'stop']


asyncio.run(main())
```

To keep an existing audit sink, combine both with
[`CompositeAuditSink`](../api/index.md#behaviorweave.CompositeAuditSink):
`CompositeAuditSink(AgxaiAuditSink(runtime), OpenTelemetryMetricsSink())`.

## Traces

Install `agxai[otel]` and `opentelemetry-exporter-otlp-proto-http`. Build an SDK
`TracerProvider`, add your span processor/exporter, then pass
`OpenTelemetryObservability(tracer_provider=provider, owns_provider=True)` as the runtime's
`observability` or the `delegate` of `BehaviorWeaveObservability`.

Each canonical execution event becomes a timestamped span. Semantic evidence and decision
artifacts are stored by agxai, not exported as canonical spans. Provider ownership controls
shutdown; close the runtime to flush owned resources.

Use an application parent span to correlate the emitted event spans into one trace. agxai
also includes application/run correlation fields in the attributes.

## Export

The [OTel example](https://github.com/smuniharish/behaviorweave/blob/master/examples/19_agxai_opentelemetry.py)
exports traces and decision metrics over OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set,
and prints span names and decision counts otherwise. Set the endpoint to
`http://127.0.0.1:4318` for a local OpenTelemetry Collector, which accepts both signals.
Shut down the `MeterProvider` on exit to flush the last metric export. Follow your exporter's
standard environment settings for headers/TLS; never put credentials in code.
