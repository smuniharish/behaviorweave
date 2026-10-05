import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, tzinfo
from enum import Enum

import pytest
from pydantic import BaseModel

from behaviorweave import (
    BehaviorEvent,
    BehaviorWeaveError,
    EventType,
    EventValidationError,
    Outcome,
)
from support import at


class _NoOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None


class _Color(Enum):
    RED = 1


class _Query(BaseModel):
    text: str
    limit: int


def test_enum_values_are_stable() -> None:
    assert [e.value for e in EventType] == [
        "tool_call",
        "node_execution",
        "agent_handoff",
        "delegation",
        "outcome",
        "retry",
        "custom",
    ]
    assert [o.value for o in Outcome] == ["success", "failure", "retry"]


def test_defaults_are_generated() -> None:
    event = BehaviorEvent(EventType.CUSTOM, scope="s")
    assert event.timestamp.utcoffset() == timedelta(0)
    assert event.event_id
    assert event.metadata == {}
    assert event.idempotency_key() == event.event_id


def test_string_enum_values_are_coerced() -> None:
    event = BehaviorEvent("outcome", scope="s", outcome="failure")  # type: ignore[arg-type]
    assert event.event_type is EventType.OUTCOME
    assert event.outcome is Outcome.FAILURE


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"event_type": "bogus"}, "event_type must be one of"),
        ({"event_type": ["unhashable"]}, "event_type must be one of"),
        ({"outcome": "maybe"}, "outcome must be one of"),
        ({"scope": ""}, "scope"),
        ({"scope": "   "}, "scope"),
        ({"scope": 7}, "scope"),
        ({"event_id": ""}, "event_id"),
        ({"event_id": 3}, "event_id"),
        ({"timestamp": datetime(2026, 1, 1)}, "timezone-aware"),  # noqa: DTZ001 - deliberately naive
        ({"timestamp": datetime(2026, 1, 1, tzinfo=_NoOffset())}, "timezone-aware"),
        ({"timestamp": "2026-01-01T00:00:00+00:00"}, "timezone-aware"),
    ],
)
def test_invalid_fields_raise(kwargs: dict[str, object], message: str) -> None:
    fields: dict[str, object] = {"event_type": EventType.CUSTOM, "scope": "s", **kwargs}
    with pytest.raises(EventValidationError, match=message) as info:
        BehaviorEvent(**fields)  # type: ignore[arg-type]
    assert isinstance(info.value, ValueError)
    assert isinstance(info.value, BehaviorWeaveError)


def test_event_is_immutable_and_metadata_is_isolated() -> None:
    source = {"k": "v"}
    event = BehaviorEvent(EventType.CUSTOM, scope="s", metadata=source)
    source["k"] = "changed"
    assert event.metadata == {"k": "v"}
    with pytest.raises(TypeError):
        event.metadata["k"] = "x"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        event.scope = "other"  # type: ignore[misc]
    assert repr(event.metadata) == "{'k': 'v'}"


def test_tool_call_fingerprint_ignores_argument_order() -> None:
    first = BehaviorEvent.tool_call("search", {"q": "a", "page": 1}, scope="s")
    second = BehaviorEvent.tool_call("search", {"page": 1, "q": "a"}, scope="s")
    third = BehaviorEvent.tool_call("search", {"page": 2, "q": "a"}, scope="s")
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != third.fingerprint
    assert first.fingerprint is not None
    assert first.fingerprint.startswith("search#")
    assert "page" not in first.fingerprint


def test_tool_call_fingerprint_handles_arbitrary_values() -> None:
    args = {
        "when": datetime(2026, 1, 1, tzinfo=UTC),
        "day": date(2026, 1, 2),
        "tags": {"b", "a"},
        "pair": (1, 2),
        "query": _Query(text="x", limit=2),
        "color": _Color.RED,
        "nested": {1: "int-key", "1": "str-key"},
        "nan": float("nan"),
    }
    first = BehaviorEvent.tool_call("t", args, scope="s")
    second = BehaviorEvent.tool_call("t", dict(reversed(list(args.items()))), scope="s")
    assert first.fingerprint == second.fingerprint
    assert BehaviorEvent.tool_call("t", {"tags": {"a", "b"}}, scope="s").fingerprint == (
        BehaviorEvent.tool_call("t", {"tags": frozenset({"b", "a"})}, scope="s").fingerprint
    )
    assert BehaviorEvent.tool_call("t", {"pair": (1, 2)}, scope="s").fingerprint == (
        BehaviorEvent.tool_call("t", {"pair": [1, 2]}, scope="s").fingerprint
    )


def test_tool_call_records_arguments_and_context() -> None:
    event = BehaviorEvent.tool_call(
        "lookup",
        {"id": 7},
        scope="s",
        event_id="e-1",
        timestamp=at(5),
        thread_id="th",
        run_id="run",
        metadata={"origin": "test", "arguments": "overwritten"},
        provenance_ref="prov",
    )
    assert event.event_type is EventType.TOOL_CALL
    assert event.tool_name == "lookup"
    assert event.metadata == {"origin": "test", "arguments": {"id": 7}}
    assert (event.event_id, event.timestamp, event.thread_id, event.run_id) == (
        "e-1",
        at(5),
        "th",
        "run",
    )
    assert event.provenance_ref == "prov"
    assert BehaviorEvent.tool_call("lookup", scope="s").metadata == {"arguments": {}}


@pytest.mark.parametrize("name", ["", "  ", None])
def test_tool_call_requires_a_tool_name(name: object) -> None:
    with pytest.raises(EventValidationError, match="tool_name"):
        BehaviorEvent.tool_call(name, scope="s")  # type: ignore[arg-type]


def test_explicit_empty_event_id_is_rejected_not_replaced() -> None:
    with pytest.raises(EventValidationError, match="event_id"):
        BehaviorEvent.tool_call("t", scope="s", event_id="")


def test_outcome_event_fields() -> None:
    meta = {"error_type": "Timeout"}
    event = BehaviorEvent.outcome_event(
        Outcome.FAILURE,
        scope="s",
        event_id="o-1",
        timestamp=at(1),
        tool_name="fetch",
        node_name="worker",
        thread_id="th",
        run_id="run",
        metadata=meta,
        provenance_ref="p",
    )
    meta["error_type"] = "changed"
    assert event.event_type is EventType.OUTCOME
    assert event.outcome is Outcome.FAILURE
    assert event.metadata == {"error_type": "Timeout"}
    assert (event.tool_name, event.node_name, event.event_id) == ("fetch", "worker", "o-1")
    assert (event.thread_id, event.run_id, event.provenance_ref) == ("th", "run", "p")
    assert BehaviorEvent.outcome_event(Outcome.SUCCESS, scope="s").metadata == {}


@pytest.mark.parametrize(
    ("event", "identity"),
    [
        (BehaviorEvent(EventType.CUSTOM, scope="s", fingerprint="fp", node_name="n"), "fp"),
        (
            BehaviorEvent(EventType.DELEGATION, scope="s", agent_name="a", target_agent="b"),
            "a->b",
        ),
        (BehaviorEvent(EventType.AGENT_HANDOFF, scope="s"), "unknown->unknown"),
        (BehaviorEvent(EventType.NODE_EXECUTION, scope="s", node_name="n"), "n"),
        (BehaviorEvent(EventType.CUSTOM, scope="s", tool_name="t"), "t"),
        (BehaviorEvent(EventType.CUSTOM, scope="s", agent_name="ag"), "ag"),
        (BehaviorEvent.outcome_event(Outcome.FAILURE, scope="s"), "failure"),
        (BehaviorEvent.outcome_event(Outcome.SUCCESS, scope="s", tool_name="t"), "t:success"),
        (BehaviorEvent(EventType.OUTCOME, scope="s"), "outcome"),
        (BehaviorEvent(EventType.RETRY, scope="s", outcome=Outcome.RETRY), "retry"),
    ],
)
def test_identity_precedence(event: BehaviorEvent, identity: str) -> None:
    assert event.identity() == identity


def test_to_dict_and_to_json_are_json_safe() -> None:
    event = BehaviorEvent(
        EventType.OUTCOME,
        scope="s",
        timestamp=at(0),
        event_id="e",
        outcome=Outcome.SUCCESS,
        metadata={"obj": object.__name__, "set": {2, 1}, "when": at(1)},
    )
    data = event.to_dict()
    assert data["event_type"] == "outcome"
    assert data["outcome"] == "success"
    assert data["timestamp"] == at(0).isoformat()
    assert data["metadata"] == {"obj": "object", "set": [1, 2], "when": at(1).isoformat()}
    assert json.loads(event.to_json()) == data
    assert BehaviorEvent(EventType.CUSTOM, scope="s").to_dict()["outcome"] is None


def test_to_json_never_fails_on_unserializable_metadata() -> None:
    event = BehaviorEvent(EventType.CUSTOM, scope="s", metadata={"x": object()})
    assert json.loads(event.to_json())["metadata"]["x"].startswith("<object object")
