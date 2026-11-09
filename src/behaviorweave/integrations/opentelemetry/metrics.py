"""Record engine decisions as OpenTelemetry metrics."""

from __future__ import annotations

try:
    from opentelemetry import metrics
except ModuleNotFoundError as exc:  # pragma: no cover - only without the otel extra
    raise ImportError(
        "behaviorweave.integrations.opentelemetry needs OpenTelemetry; "
        "install it with: pip install 'behaviorweave[otel]'"
    ) from exc

from ... import __version__
from ...audit import AuditSink
from ...errors import PolicyConfigurationError
from ...interventions import AuditRecord

__all__ = ["DECISIONS_METRIC", "OpenTelemetryMetricsSink"]

DECISIONS_METRIC = "behaviorweave.decisions"
"""Name of the counter of processed events, one per decision."""


class OpenTelemetryMetricsSink(AuditSink):
    """An [`AuditSink`][behaviorweave.AuditSink] that counts decisions with OpenTelemetry.

    Every audit record adds one to the ``behaviorweave.decisions`` counter, with these
    attributes:

    - ``behaviorweave.event.type``: the event type, such as ``tool_call``;
    - ``behaviorweave.intervention``: the intervention kind, such as ``noop`` or ``halt``;
    - ``behaviorweave.pattern`` and ``behaviorweave.policy``: the deciding pattern and
      policy, present only when one decided;
    - ``behaviorweave.actionable``, ``behaviorweave.suppressed``, and
      ``behaviorweave.duplicate``: the decision's flags.

    Scopes and event IDs are never recorded, so the number of time series stays bounded by
    your configuration. Combine the sink with a durable audit sink through
    [`CompositeAuditSink`][behaviorweave.CompositeAuditSink]. Exporting, flushing, and
    shutting down belong to the meter provider; `flush` and `close` do nothing.

    Args:
        meter_provider: The meter provider to record with. Defaults to the global one set
            with ``opentelemetry.metrics.set_meter_provider``.

    Raises:
        PolicyConfigurationError: If ``meter_provider`` is not an OpenTelemetry
            ``MeterProvider``.
    """

    def __init__(self, *, meter_provider: metrics.MeterProvider | None = None) -> None:
        if meter_provider is not None and not isinstance(meter_provider, metrics.MeterProvider):
            raise PolicyConfigurationError(
                f"meter_provider must be an OpenTelemetry MeterProvider, "
                f"not {type(meter_provider).__name__}"
            )
        meter = metrics.get_meter("behaviorweave", __version__, meter_provider=meter_provider)
        self._decisions = meter.create_counter(
            DECISIONS_METRIC,
            unit="{decision}",
            description="Events processed by the BehaviorWeave engine, by decision.",
        )

    async def write(self, record: AuditRecord) -> None:
        """Count ``record``'s decision."""
        decision = record.decision
        intervention = decision.intervention
        attributes: dict[str, str | bool] = {
            "behaviorweave.event.type": record.event.event_type.value,
            "behaviorweave.intervention": intervention.kind.value,
            "behaviorweave.actionable": decision.actionable,
            "behaviorweave.suppressed": decision.suppressed,
            "behaviorweave.duplicate": decision.duplicate,
        }
        if intervention.pattern is not None:
            attributes["behaviorweave.pattern"] = intervention.pattern
        if intervention.policy is not None:
            attributes["behaviorweave.policy"] = intervention.policy
        self._decisions.add(1, attributes)
