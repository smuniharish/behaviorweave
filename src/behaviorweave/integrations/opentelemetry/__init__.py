"""OpenTelemetry integration: decision metrics. Install with ``behaviorweave[otel]``."""

from .metrics import DECISIONS_METRIC, OpenTelemetryMetricsSink

__all__ = ["DECISIONS_METRIC", "OpenTelemetryMetricsSink"]
