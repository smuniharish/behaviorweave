# BehaviorWeave

Behavioral policy and intervention framework for LangGraph and LangChain agents.

BehaviorWeave observes normalized execution events, detects deterministic behavioral
patterns, evaluates explicit policies, and emits intervention decisions. It does not
execute interventions, replace LangGraph, capture chain-of-thought, or require LangSmith.

## Why BehaviorWeave?

Agent frameworks are designed to execute models, tools, routing, and graph transitions.
They intentionally leave application-specific behavioral governance to the host system.
That creates a gap when an otherwise capable agent starts repeating a tool call, cycling
through retries, repeatedly delegating work, or continuing after a failure streak.

BehaviorWeave fills that gap with a small, deterministic policy layer:

- **Make recurring behavior explicit.** Normalize observable tool calls, node execution,
  outcomes, retries, and delegations into events that can be evaluated consistently.
- **Keep decisions explainable.** Policies map known patterns and thresholds to a
  structured intervention with the pattern, count, scope, reason, and policy ID.
- **Preserve framework ownership.** LangChain and LangGraph still own agent execution,
  tool invocation, routing, persistence, and interrupts. Your application decides how
  to apply a `nudge`, `pause`, `human_review`, or `stop` decision.
- **Avoid prompt-only guardrails.** A prompt can ask an agent not to repeat itself, but
  it cannot provide deterministic, scope-isolated behavioral history at the runtime
  boundary.
- **Support progressive intervention.** Start with a nudge, escalate after continued
  behavior, or require human review without embedding policy logic into every tool or
  graph node.

Use BehaviorWeave when you need deterministic operational controls around observable
agent behavior. It is not a replacement for model safety controls, authorization,
schema validation, LangGraph persistence, or a general-purpose event-processing system.

## Architecture

```text
LangGraph/LangChain -> langgraph-xai context -> BehaviorEvent
  -> fingerprint -> pattern state -> policy -> InterventionDecision -> host runtime
```

The core is framework-neutral internally. Adapters at `behaviorweave.integrations`
translate framework callbacks and preserve provenance references supplied by
`langgraph-xai`.

## Quickstart

```python
from behaviorweave import BehaviorEngine, BehaviorEvent, EventType, PolicyRule, InterventionType

engine = BehaviorEngine(
    policies=[PolicyRule("repeat-tool", "repeated_tool_call", 3, InterventionType.NUDGE)]
)
for i in range(3):
    decision = engine.process(BehaviorEvent.tool_call("get_alarm", {"machine": "ETCH-3"},
                                                     scope="thread-1"))
assert decision.intervention.kind is InterventionType.NUDGE
```

Install with `uv sync`; see [docs](docs/index.md) for the full architecture and integrations.

## Live integrations

The checked-in tests are deterministic. The real execution examples construct LangChain
v1 agents, call actual LangChain tools, and apply BehaviorWeave at the tool/delegation
boundary. See [live examples](docs/live-examples.md) for the opt-in real model setup;
provider credentials are read only from the environment.

## License

Apache License 2.0. See [LICENSE](LICENSE).
