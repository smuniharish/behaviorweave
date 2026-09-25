# BehaviorWeave integration guide

BehaviorWeave is integrated at the observable runtime boundary. The most common patterns are:

- before a tool call is sent to the runtime; emit a `BehaviorEvent.tool_call(...)`
- after an outcome is known; emit `BehaviorEvent.outcome_event(...)`
- around a delegated or handoff step; emit a delegation or agent-handoff event
- inside a LangChain or LangGraph adapter that converts framework events into the shared model

The public constructor is intentionally straightforward:

```python
from behaviorweave import BehaviorEngine, PolicyRule, InterventionType

engine = BehaviorEngine(
    policies=[
        PolicyRule(
            policy_id="repeat-lookup-nudge",
            pattern_id="repeated_tool_call",
            threshold=3,
            intervention=InterventionType.NUDGE,
        )
    ]
)
```

Use a stable, application-chosen `scope` such as a LangGraph thread ID, LangChain run ID, tenant ID, or session key. Keep the same scope across all relevant events so the pattern state remains accurate.

The host runtime decides whether to apply the returned intervention by nudging the model, pausing work, escalating to human review, or stopping execution.

See the quickstart and live examples in [Quickstart](https://behaviorweave.readthedocs.io/en/latest/quickstart/) and [Live examples](https://behaviorweave.readthedocs.io/en/latest/live-examples/), along with the package `src/behaviorweave/` modules, for the verified integration flow.
