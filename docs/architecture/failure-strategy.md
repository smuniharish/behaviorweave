# Failure semantics

BehaviorWeave fails loudly and early. It never silently fails open, never fabricates
evidence, and never executes an intervention on its own.

## Error hierarchy

Every exception derives from [`BehaviorWeaveError`][behaviorweave.BehaviorWeaveError]. Each
concrete error is also a `ValueError`, because it always reports invalid input or
configuration.

| Exception | Raised when |
| --- | --- |
| [`EventValidationError`][behaviorweave.EventValidationError] | An event has an empty scope or event ID, a naive timestamp, or an unknown event type or outcome; an adapter receives an unusable payload; the middleware cannot determine a scope. |
| [`PolicyConfigurationError`][behaviorweave.PolicyConfigurationError] | A rule or pattern is invalid, IDs repeat, or a policy references a pattern the engine does not provide. Raised at construction time. |
| [`StateStoreError`][behaviorweave.StateStoreError] | A state is invalid (for example, a negative count), cannot be deserialized, or a store receives a value that is not a `BehaviorState`. |

```python
from behaviorweave import (
    BehaviorEngine,
    BehaviorWeaveError,
    InterventionType,
    PolicyRule,
)

try:
    BehaviorEngine(
        policies=[
            PolicyRule("p", "repeated_tool_calls", 2, InterventionType.NUDGE)
        ]
    )
except BehaviorWeaveError as error:
    print(type(error).__name__)  # PolicyConfigurationError
```

## Runtime failures

- **Configuration errors** surface when the engine is created, never mid-run.
- **Store and pattern errors** propagate from `BehaviorEngine.process` with their original
  cause. The engine does not swallow them, so a broken durable store cannot silently disable
  your policies.
- **Audit sink errors** propagate to the caller after the decision is recorded. Processing
  the same event again returns that decision, so no intervention is lost.
- **Tool errors** under `BehaviorWeaveMiddleware` are recorded as failure outcomes before the
  exception propagates unchanged. LangGraph interrupts are not errors: they propagate without
  being recorded.

## Choosing a host policy

Because errors propagate, the host decides how to degrade. A service that prefers
availability can catch `BehaviorWeaveError` around `process` and continue without a
decision; a safety-critical workflow can treat any error as a `stop`.
