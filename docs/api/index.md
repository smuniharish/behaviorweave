# API reference

Every name on this page is importable from the package root, `behaviorweave`, unless it is
listed under an integration. Names that are not documented here are internal and may change
without notice.

## Engine

::: behaviorweave.BehaviorEngine

::: behaviorweave.AuditSink

::: behaviorweave.CompositeAuditSink

::: behaviorweave.InMemoryAuditSink

::: behaviorweave.__version__

## Events

::: behaviorweave.BehaviorEvent

::: behaviorweave.EventType

::: behaviorweave.Outcome

## Patterns

::: behaviorweave.built_in_patterns

::: behaviorweave.Pattern

::: behaviorweave.PatternObservation

::: behaviorweave.ConsecutivePattern

::: behaviorweave.StreakPattern

::: behaviorweave.OscillationPattern

::: behaviorweave.FrequencyPattern

## Policies

::: behaviorweave.PolicyRule

::: behaviorweave.PolicyEngine

## Decisions

::: behaviorweave.InterventionType

::: behaviorweave.Intervention

::: behaviorweave.InterventionDecision

::: behaviorweave.Explanation

::: behaviorweave.AuditRecord

## State

::: behaviorweave.BehaviorState

::: behaviorweave.BehaviorStateStore

::: behaviorweave.InMemoryBehaviorStateStore

## Errors

::: behaviorweave.BehaviorWeaveError

::: behaviorweave.EventValidationError

::: behaviorweave.PolicyConfigurationError

::: behaviorweave.StateStoreError

## Integrations

### LangChain

`from behaviorweave.integrations.langchain import ...`

::: behaviorweave.integrations.langchain.BehaviorWeaveMiddleware
    options:
      heading_level: 4

::: behaviorweave.integrations.langchain.default_guidance
    options:
      heading_level: 4

::: behaviorweave.integrations.langchain.LangChainEventAdapter
    options:
      heading_level: 4

### LangGraph

`from behaviorweave.integrations.langgraph import ...`

::: behaviorweave.integrations.langgraph.LangGraphEventAdapter
    options:
      heading_level: 4

::: behaviorweave.integrations.langgraph.LangGraphBehaviorStateStore
    options:
      heading_level: 4

### agxai

`from behaviorweave.integrations.agxai import ...`

::: behaviorweave.integrations.agxai.AgxaiEventAdapter
    options:
      heading_level: 4

::: behaviorweave.integrations.agxai.create_agxai_runtime
    options:
      heading_level: 4

::: behaviorweave.integrations.agxai.instrument_graph
    options:
      heading_level: 4

::: behaviorweave.integrations.agxai.AgxaiAuditSink
    options:
      heading_level: 4

::: behaviorweave.integrations.agxai.BehaviorWeaveObservability
    options:
      heading_level: 4

::: behaviorweave.integrations.agxai.DecisionHook
    options:
      heading_level: 4

::: behaviorweave.integrations.agxai.ScopeResolver
    options:
      heading_level: 4

::: behaviorweave.integrations.agxai.thread_scope
    options:
      heading_level: 4

### OpenTelemetry

`from behaviorweave.integrations.opentelemetry import ...` Requires the `otel` extra: `pip install "behaviorweave[otel]"`.

::: behaviorweave.integrations.opentelemetry.OpenTelemetryMetricsSink
    options:
      heading_level: 4

::: behaviorweave.integrations.opentelemetry.DECISIONS_METRIC
    options:
      heading_level: 4

## Extension contracts

::: behaviorweave.testing.BehaviorStateStoreContract

::: behaviorweave.testing.PatternContract
