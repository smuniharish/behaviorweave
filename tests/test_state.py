import json
from datetime import timedelta

import pytest

from behaviorweave import BehaviorState, InMemoryBehaviorStateStore, StateStoreError
from support import ManualClock, at


def _state(**overrides: object) -> BehaviorState:
    fields: dict[str, object] = {"pattern_id": "p", "scope": "s", "count": 1, **overrides}
    return BehaviorState(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["count", "event_count", "version"])
def test_negative_counters_are_rejected(field: str) -> None:
    with pytest.raises(StateStoreError, match="non-negative"):
        _state(**{field: -1})


def test_state_normalizes_containers() -> None:
    cooldowns = {"policy": at(10)}
    state = _state(
        cooldowns=cooldowns,
        intervention_history=["a"],
        seen_event_ids=["e"],
        emissions=[["e", "a", 1, "r"]],
        metadata={"k": [1]},
    )
    assert state.emissions == (("e", "a", 1, "r"),)
    cooldowns["other"] = at(20)
    assert state.cooldowns == {"policy": at(10)}
    assert state.intervention_history == ("a",)
    assert state.seen_event_ids == ("e",)
    with pytest.raises(TypeError):
        state.cooldowns["x"] = at(0)  # type: ignore[index]
    assert _state().metadata == {}


def test_json_round_trip_preserves_every_field() -> None:
    state = BehaviorState(
        pattern_id="p",
        scope="s",
        count=3,
        first_seen=at(1),
        last_seen=at(2),
        previous_fingerprint="a",
        current_fingerprint="b",
        event_count=4,
        intervention_history=("nudge",),
        cooldowns={"nudge": at(60)},
        seen_event_ids=("e1", "e2"),
        emissions=(("e2", "nudge", 3, "repeated"),),
        metadata={"note": "x"},
        version=5,
    )
    assert BehaviorState.from_json(state.to_json()) == state
    assert BehaviorState.from_dict(state.to_dict()) == state
    assert json.loads(state.to_json())["cooldowns"] == {"nudge": at(60).isoformat()}
    assert json.loads(state.to_json())["emissions"] == [["e2", "nudge", 3, "repeated"]]


def test_from_dict_applies_defaults_and_ignores_unknown_keys() -> None:
    restored = BehaviorState.from_dict({"pattern_id": "p", "scope": "s", "future_field": 1})
    assert restored == BehaviorState(pattern_id="p", scope="s")


@pytest.mark.parametrize(
    "data",
    [
        {"scope": "s"},
        {"pattern_id": "p", "scope": "s", "count": "many"},
        {"pattern_id": "p", "scope": "s", "count": -2},
        {"pattern_id": "p", "scope": "s", "last_seen": "not-a-date"},
        {"pattern_id": "p", "scope": "s", "last_seen": "2026-01-01T00:00:00"},
        {"pattern_id": "p", "scope": "s", "cooldowns": {"a": "2026-01-01T00:00:00"}},
        {"pattern_id": "p", "scope": "s", "cooldowns": ["not", "a", "mapping"]},
        {"pattern_id": "p", "scope": "s", "emissions": ["e"]},
        {"pattern_id": "p", "scope": "s", "emissions": [["e", "nudge", 1]]},
        {"pattern_id": "p", "scope": "s", "emissions": [["e", "nudge", "many", "r"]]},
    ],
)
def test_from_dict_rejects_malformed_states(data: dict[str, object]) -> None:
    with pytest.raises(StateStoreError):
        BehaviorState.from_dict(data)


@pytest.mark.parametrize("raw", ["{not json", "[1, 2]", b"null"])
def test_from_json_rejects_malformed_documents(raw: str | bytes) -> None:
    with pytest.raises(StateStoreError):
        BehaviorState.from_json(raw)


def test_store_crud() -> None:
    store = InMemoryBehaviorStateStore()
    assert store.get("k") is None
    store.put("k", _state())
    assert store.get("k") == _state()
    updated = store.update("k", lambda current: _state(count=(current.count if current else 0) + 1))
    assert updated.count == 2
    assert store.update("new", lambda current: _state(count=0 if current is None else 9)).count == 0
    store.delete("k")
    store.delete("missing")
    assert store.get("k") is None


def test_store_rejects_non_state_values() -> None:
    store = InMemoryBehaviorStateStore()
    with pytest.raises(StateStoreError):
        store.put("k", "state")  # type: ignore[arg-type]
    with pytest.raises(StateStoreError):
        store.update("k", lambda current: "state")  # type: ignore[arg-type, return-value]


def test_store_isolates_nested_metadata() -> None:
    store = InMemoryBehaviorStateStore()
    payload = {"items": [1]}
    store.put("k", _state(metadata={"payload": payload}))
    payload["items"].append(2)
    fetched = store.get("k")
    assert fetched is not None
    fetched.metadata["payload"]["items"].append(3)  # type: ignore[index]
    again = store.get("k")
    assert again is not None
    assert again.metadata == {"payload": {"items": [1]}}


def test_store_clear_all_and_by_scope() -> None:
    store = InMemoryBehaviorStateStore()
    store.put("a1", _state(scope="a"))
    store.put("a2", _state(scope="a"))
    store.put("b1", _state(scope="b"))
    assert store.clear("a") == 2
    assert store.get("a1") is None
    assert store.get("b1") is not None
    assert store.clear("missing") == 0
    assert store.clear() == 1
    assert store.get("b1") is None


def test_clear_drops_expired_states_without_counting_them() -> None:
    clock = ManualClock()
    store = InMemoryBehaviorStateStore(ttl=timedelta(seconds=10), clock=clock)
    store.put("a-old", _state(scope="a"))
    store.put("b-old", _state(scope="b"))
    clock.advance(seconds=11)
    store.put("a-new", _state(scope="a"))
    assert store.clear("a") == 1
    assert store.clear() == 0
    assert store._states == {}


@pytest.mark.parametrize("ttl", [timedelta(0), timedelta(seconds=-1)])
def test_ttl_must_be_positive(ttl: timedelta) -> None:
    with pytest.raises(StateStoreError, match="ttl"):
        InMemoryBehaviorStateStore(ttl=ttl)


def test_ttl_expiry_is_sliding_and_purgeable() -> None:
    clock = ManualClock()
    store = InMemoryBehaviorStateStore(ttl=timedelta(seconds=10), clock=clock)
    store.put("k", _state())
    clock.advance(seconds=9)
    store.update("k", lambda current: _state(count=2))
    clock.advance(seconds=9)
    assert store.get("k") is not None, "writes refresh the TTL"
    clock.advance(seconds=1)
    assert store.get("k") is None
    store.put("a", _state())
    store.put("b", _state())
    assert store.purge_expired() == 0
    clock.advance(seconds=10)
    assert store.purge_expired() == 2


def test_ttl_uses_wall_clock_by_default() -> None:
    store = InMemoryBehaviorStateStore(ttl=timedelta(hours=1))
    store.put("k", _state())
    assert store.get("k") == _state()
    assert store.purge_expired() == 0


def test_expired_entries_are_purged_periodically() -> None:
    clock = ManualClock()
    store = InMemoryBehaviorStateStore(ttl=timedelta(seconds=1), clock=clock)
    store.put("stale", _state())
    clock.advance(seconds=2)
    for index in range(InMemoryBehaviorStateStore._PURGE_EVERY - 1):
        store.put(f"fresh-{index}", _state())
    assert "stale" not in store._states
