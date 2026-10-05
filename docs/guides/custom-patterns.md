# Custom patterns

Most needs are covered by configuring the public pattern classes
(`ConsecutivePattern`, `StreakPattern`, `OscillationPattern`, `FrequencyPattern`) with your
own IDs and event types; see [Patterns](../patterns.md#configuring-your-own-instances). When
you need a different notion of "what is happening", implement the
[`Pattern`][behaviorweave.Pattern] protocol.

## The protocol

A pattern has a unique `pattern_id` and two methods:

- `matches(event)` returns whether the pattern observes the event. Keep it cheap and pure.
- `observe(event, store)` advances the pattern's state through
  `store.update(key, fn)` and returns a
  [`PatternObservation`][behaviorweave.PatternObservation].

Follow these rules so your pattern composes with the engine's guarantees:

1. **Advance state only inside `store.update`.** The function you pass is applied
   atomically; compute the next state from the `current` state it receives.
2. **Derive the next state with `dataclasses.replace`.** The engine keeps its policy
   bookkeeping (fired policies, cooldowns, and recently emitted decisions) in the same
   state. `replace` carries those fields forward; building a fresh `BehaviorState` would
   reset cooldowns and once-only history.
3. **Honor idempotency.** If `event.event_id` is already in `current.seen_event_ids`,
   return `current` unchanged and report `accepted=False`. Keep the 256 most recent IDs.
4. **Scope your key.** Include `event.scope` in the state key so histories never leak
   between scopes.
5. **Be deterministic.** The same event sequence must always produce the same counts.

## Example: consecutive destructive operations

This pattern counts consecutive tool calls whose name marks them as destructive, and
resets on any other tool call:

```python
from dataclasses import replace

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    BehaviorStateStore,
    EventType,
    InterventionType,
    PatternObservation,
    PolicyRule,
)


class DestructiveStreak:
    pattern_id = "destructive_streak"

    def matches(self, event: BehaviorEvent) -> bool:
        return event.event_type is EventType.TOOL_CALL

    def observe(
        self, event: BehaviorEvent, store: BehaviorStateStore
    ) -> PatternObservation:
        destructive = (event.tool_name or "").startswith(("delete_", "drop_"))
        accepted = False

        def advance(current: BehaviorState | None) -> BehaviorState:
            nonlocal accepted
            if current is None:
                current = BehaviorState(self.pattern_id, event.scope)
            elif event.event_id in current.seen_event_ids:
                return current
            accepted = True
            return replace(
                current,
                count=current.count + 1 if destructive else 0,
                last_seen=event.timestamp,
                event_count=current.event_count + 1,
                seen_event_ids=(
                    *current.seen_event_ids[-255:],
                    event.event_id,
                ),
                version=current.version + 1,
            )

        key = f"{event.scope}|{self.pattern_id}"
        state = store.update(key, advance)
        return PatternObservation(
            pattern_id=self.pattern_id,
            scope=event.scope,
            fingerprint=event.identity(),
            state_key=key,
            count=state.count,
            accepted=accepted,
            state=state,
            reason=f"{state.count} consecutive destructive tool calls",
        )


engine = BehaviorEngine(
    patterns=[DestructiveStreak()],
    policies=[
        PolicyRule(
            "confirm", "destructive_streak", 2, InterventionType.HUMAN_REVIEW
        )
    ],
)
calls = ["delete_user", "read_user", "delete_user", "drop_table"]
print(
    [
        engine.process(
            BehaviorEvent.tool_call(c, scope="s")
        ).intervention.kind.value
        for c in calls
    ]
)  # ['noop', 'noop', 'noop', 'human_review']
```

To combine a custom pattern with the built-ins, pass
`patterns=[*built_in_patterns(), DestructiveStreak()]`.
