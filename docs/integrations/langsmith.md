# LangSmith

Install `agxai[langsmith]` and construct agxai's `LangSmithObservability` with your configured
client/project. Pass it to `create_agxai_runtime(observability=...)` or as the `delegate` of
`BehaviorWeaveObservability`. No exporter options are copied or restricted by BehaviorWeave.

Use LangSmith's supported environment-based credential settings. Keep exporter lifecycle
ownership explicit and `await runtime.close()` after execution.

See the [agxai integration](agxai.md) and
[agxai LangSmith guide](https://agxai.readthedocs.io/en/latest/integrations/langsmith/)
for the downstream provider's configuration and data-handling behavior.
