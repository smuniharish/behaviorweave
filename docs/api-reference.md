# API reference

Every name on this page is importable from the package root, `behaviorweave`, unless it is
listed under an integration. Names that are not documented here are internal and may change
without notice.

## Engine

::: behaviorweave.BehaviorEngine

::: behaviorweave.AuditSink

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

### langgraph-xai

`from behaviorweave.integrations.langgraph_xai import ...`

::: behaviorweave.integrations.langgraph_xai.LangGraphXAIEventAdapter
    options:
      heading_level: 4
