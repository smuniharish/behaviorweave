from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    EventType,
    InterventionType,
    PolicyRule,
)
from behaviorweave.state import InMemoryBehaviorStateStore


def test_repeated_tool_regression_and_escalation():
    engine = BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 3, InterventionType.NUDGE),
            PolicyRule("synthesis", "repeated_tool_call", 5, InterventionType.FORCE_SYNTHESIS),
        ]
    )
    decisions = [
        engine.process(BehaviorEvent.tool_call("get_alarm", {"machine": "ETCH-3"}, scope="t"))
        for _ in range(5)
    ]
    assert decisions[2].intervention.kind is InterventionType.NUDGE
    assert decisions[4].intervention.kind is InterventionType.FORCE_SYNTHESIS


def test_scopes_are_isolated():
    engine = BehaviorEngine(
        policies=[PolicyRule("nudge", "repeated_tool_call", 3, InterventionType.NUDGE)]
    )
    for _ in range(3):
        result = engine.process(BehaviorEvent.tool_call("x", scope="a"))
    other = engine.process(BehaviorEvent.tool_call("x", scope="b"))
    assert result.intervention.kind is InterventionType.NUDGE
    assert other.intervention.kind is InterventionType.NOOP


def test_duplicate_event_is_idempotent():
    engine = BehaviorEngine()
    event = BehaviorEvent.tool_call("x", scope="t", event_id="same")
    engine.process(event)
    engine.process(event)
    state = engine.store.get("t:repeated_tool_call")
    assert state is not None
    assert state.count == 1


def test_consecutive_streak_resets_when_fingerprint_changes():
    engine = BehaviorEngine()
    engine.process(BehaviorEvent.tool_call("get_alarm", {"machine": "ETCH-3"}, scope="t"))
    engine.process(BehaviorEvent.tool_call("get_alarm", {"machine": "ETCH-4"}, scope="t"))
    engine.process(BehaviorEvent.tool_call("get_alarm", {"machine": "ETCH-3"}, scope="t"))
    state = engine.store.get("t:repeated_tool_call")
    assert state is not None
    assert state.count == 1


def test_policy_cooldown_is_preserved_through_state_updates():
    engine = BehaviorEngine(
        policies=[
            PolicyRule(
                "nudge",
                "repeated_tool_call",
                2,
                InterventionType.NUDGE,
                cooldown=timedelta(minutes=1),
            )
        ]
    )
    engine.process(BehaviorEvent.tool_call("get_alarm", scope="t"))
    emitted = engine.process(BehaviorEvent.tool_call("get_alarm", scope="t"))
    suppressed = engine.process(BehaviorEvent.tool_call("get_alarm", scope="t"))
    assert emitted.intervention.kind is InterventionType.NUDGE
    assert suppressed.suppressed


def test_concurrent_updates_are_atomic():
    store = InMemoryBehaviorStateStore()
    engine = BehaviorEngine(state_store=store)
    events = [
        BehaviorEvent(EventType.NODE_EXECUTION, scope="t", node_name="worker", event_id=str(i))
        for i in range(100)
    ]
    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(engine.process, events))
    state = store.get("t:repeated_node_execution")
    assert state is not None
    assert state.count == 100
