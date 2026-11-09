# Langfuse

Install `agxai[langfuse]`, construct agxai's `LangfuseObservability` with your configured
client, and supply it to `create_agxai_runtime(observability=...)` or as the `delegate` of
`BehaviorWeaveObservability`. Every downstream exporter option remains available on that
provider; BehaviorWeave does not create a second client or impose hidden defaults.

Read keys/host settings from the environment, configure sanitization and retention for
your deployment, and close the runtime to flush resources it owns.

See the [agxai integration](agxai.md) and
[agxai Langfuse guide](https://agxai.readthedocs.io/en/latest/integrations/langfuse/).
