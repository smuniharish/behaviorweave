# OpenTelemetry

Install `agxai[otel]` and `opentelemetry-exporter-otlp-proto-http`. Build an SDK
`TracerProvider`, add your span processor/exporter, then pass
`OpenTelemetryObservability(tracer_provider=provider, owns_provider=True)` as the runtime's
`observability` or the `delegate` of `BehaviorWeaveObservability`.

Each canonical execution event becomes a timestamped span. Semantic evidence and decision
artifacts are stored by agxai, not exported as canonical spans. Provider ownership controls
shutdown; close the runtime to flush owned resources.

The [OTel example](https://github.com/smuniharish/behaviorweave/blob/master/examples/19_agxai_opentelemetry.py)
uses OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and prints spans otherwise.
Set the endpoint to `http://127.0.0.1:4318` for a local collector or Jaeger. Follow your
exporter's standard environment settings for headers/TLS; never put credentials in code.

Use an application parent span to correlate the emitted event spans into one trace. agxai
also includes application/run correlation fields in the attributes.
