from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID, uuid4

import pytest
from langchain.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph_xai import (
    ExecutionContext,
    ExecutionStatus,
    NodeExecution,
    ProvenanceStore,
    Run,
    StoreFilter,
    ToolExecution,
    ToolStatus,
    XAIRuntime,
)
from langgraph_xai.core import (
    ExceptionEvent,
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionStartedEvent,
    NodeExecutionEvent,
    ToolExecutionEvent,
    XAIEvent,
)

from behaviorweave import (
    BehaviorEngine,
    EventType,
    EventValidationError,
    InterventionType,
    Outcome,
    PolicyRule,
)
from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter
from support import at

CONTEXT = ExecutionContext(application_id="app", tenant_id="t", graph_id="g", thread_id="th-1")
ADAPTER = LangGraphXAIEventAdapter()


def _tool_event(status: ToolStatus, name: str = "get_alarm") -> ToolExecutionEvent:
    execution = ToolExecution(context=CONTEXT, tool_id="tid", tool_name=name, status=status)
    return ToolExecutionEvent(context=CONTEXT, sequence=2, tool=execution)


def _node_event(status: ExecutionStatus, node_id: str = "agent") -> NodeExecutionEvent:
    node = NodeExecution(context=CONTEXT, node_id=node_id, status=status, started_at=at(0))
    return NodeExecutionEvent(context=CONTEXT, sequence=1, node=node)


def _failed_run(exception_type: str) -> ExecutionFailedEvent:
    error = ExceptionEvent(context=CONTEXT, exception_type=exception_type, message="x")
    return ExecutionFailedEvent(context=CONTEXT, sequence=3, error=error)


def test_tool_execution_events_keep_their_identity_and_provenance() -> None:
    xai_event = _tool_event(ToolStatus.FAILED)

    event = ADAPTER.event(xai_event, scope="s")

    assert event.event_type is EventType.TOOL_CALL
    assert (event.tool_name, event.outcome) == ("get_alarm", Outcome.FAILURE)
    assert event.event_id == event.provenance_ref == str(xai_event.id)
    assert event.timestamp == xai_event.timestamp
    assert (event.thread_id, event.run_id) == ("th-1", str(CONTEXT.run_id))
    assert event.metadata == {
        "source": "langgraph-xai",
        "xai_event_type": "tool.execution",
        "sequence": 2,
    }


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (ToolStatus.SUCCEEDED, Outcome.SUCCESS),
        (ToolStatus.FAILED, Outcome.FAILURE),
        (ToolStatus.TIMED_OUT, Outcome.FAILURE),
        (ToolStatus.CANCELLED, None),
    ],
)
def test_every_tool_status_maps_to_an_outcome(status: ToolStatus, outcome: Outcome | None) -> None:
    assert ADAPTER.event(_tool_event(status), scope="s").outcome is outcome
    assert ADAPTER.event(_tool_event(status).model_dump(), scope="s").outcome is outcome


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (ExecutionStatus.COMPLETED, Outcome.SUCCESS),
        (ExecutionStatus.FAILED, Outcome.FAILURE),
        (ExecutionStatus.RUNNING, None),
        (ExecutionStatus.CANCELLED, None),
        (ExecutionStatus.INTERRUPTED, None),
    ],
)
def test_every_node_status_maps_to_an_outcome(
    status: ExecutionStatus, outcome: Outcome | None
) -> None:
    event = ADAPTER.event(_node_event(status), scope="s")
    dumped = ADAPTER.event(_node_event(status).model_dump(mode="json"), scope="s")

    assert (event.event_type, event.node_name, event.outcome) == (
        EventType.NODE_EXECUTION,
        "agent",
        outcome,
    )
    assert (dumped.node_name, dumped.outcome) == ("agent", outcome)


def test_run_events_map_to_outcomes_and_cancellation_is_not_a_failure() -> None:
    completed = ADAPTER.event(ExecutionCompletedEvent(context=CONTEXT, sequence=4), scope="s")
    failed = ADAPTER.event(_failed_run("ValueError"), scope="s")

    assert (completed.event_type, completed.outcome) == (EventType.OUTCOME, Outcome.SUCCESS)
    assert (failed.event_type, failed.outcome) == (EventType.OUTCOME, Outcome.FAILURE)
    for cancellation in ("CancelledError", "GeneratorExit", "KeyboardInterrupt"):
        cancelled = ADAPTER.event(_failed_run(cancellation), scope="s")
        assert (cancelled.event_type, cancelled.outcome) == (EventType.OUTCOME, None)
    malformed = {"event_type": "execution.failed", "error": {"exception_type": ["x"]}}
    assert ADAPTER.event(malformed, scope="s").outcome is Outcome.FAILURE


def test_other_canonical_events_are_custom() -> None:
    event = ADAPTER.event(ExecutionStartedEvent(context=CONTEXT, sequence=0), scope="s")

    assert (event.event_type, event.outcome) == (EventType.CUSTOM, None)
    assert event.metadata["xai_event_type"] == "execution.started"


def test_plain_mappings_and_native_event_types() -> None:
    delegation = ADAPTER.event(
        {
            "event_type": "delegation",
            "agent_name": "lead",
            "target_agent": "researcher",
            "id": "d-1",
            "thread_id": "th",
            "run_id": "run",
            "timestamp": "2026-01-01T00:00:05+00:00",
        },
        scope="s",
        provenance_ref="explicit",
    )
    assert delegation.event_type is EventType.DELEGATION
    assert delegation.identity() == "lead->researcher"
    assert (delegation.event_id, delegation.provenance_ref) == ("d-1", "explicit")
    assert (delegation.thread_id, delegation.run_id, delegation.timestamp) == ("th", "run", at(5))
    outcome = ADAPTER.event({"event_type": "outcome", "outcome": "retry"}, scope="s")
    assert outcome.outcome is Outcome.RETRY
    node = ADAPTER.event({"event_type": "node_execution", "node_name": "plan"}, scope="s")
    assert (node.event_type, node.node_name) == (EventType.NODE_EXECUTION, "plan")
    custom = ADAPTER.event({"event_type": "state.transition", "outcome": "unknown"}, scope="s")
    assert (custom.event_type, custom.outcome) == (EventType.CUSTOM, None)
    assert custom.provenance_ref is None
    assert UUID(custom.event_id)
    assert ADAPTER.event({}, scope="s").event_type is EventType.CUSTOM
    assert ADAPTER.event({"event_type": "x", "sequence": True}, scope="s").metadata == {
        "source": "langgraph-xai",
        "xai_event_type": "x",
    }


@pytest.mark.parametrize(
    "timestamp",
    [None, "not-a-date", "2026-01-01T00:00:00", datetime(2026, 1, 1)],  # noqa: DTZ001 - deliberately naive
)
def test_unusable_timestamps_fall_back_to_now(timestamp: object) -> None:
    before = datetime.now(UTC)
    event = ADAPTER.event({"timestamp": timestamp}, scope="s")
    assert event.timestamp >= before


def test_invalid_payloads_are_rejected() -> None:
    class NotAModel:
        def model_dump(self) -> list[int]:
            return [1]

    with pytest.raises(EventValidationError, match="mapping or a Pydantic model"):
        ADAPTER.event(42, scope="s")
    with pytest.raises(EventValidationError):
        ADAPTER.event(NotAModel(), scope="s")


def test_replayed_xai_events_are_deduplicated() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 2, InterventionType.NUDGE)]
    )
    xai_event = _tool_event(ToolStatus.SUCCEEDED)
    first = engine.process(ADAPTER.event(xai_event, scope="s"))
    replay = engine.process(ADAPTER.event(xai_event.model_dump(), scope="s"))
    assert not first.actionable
    assert replay.duplicate
    nudge = engine.process(ADAPTER.event(_tool_event(ToolStatus.SUCCEEDED), scope="s"))
    assert nudge.intervention.kind is InterventionType.NUDGE
    assert nudge.explanation is not None
    assert nudge.explanation.provenance_ref


class EchoState(TypedDict):
    text: str


def _echo_graph() -> Any:
    builder = StateGraph(EchoState)
    builder.add_node("echo", lambda state: {"text": state["text"].upper()})
    builder.add_edge(START, "echo")
    builder.add_edge("echo", END)
    return builder.compile()


def test_instrument_graph_with_default_and_custom_runtime() -> None:
    instrumented = LangGraphXAIEventAdapter.instrument_graph(_echo_graph(), graph_id=f"g-{uuid4()}")
    assert instrumented.invoke({"text": "ok"}) == {"text": "OK"}
    assert isinstance(instrumented.runtime, XAIRuntime)
    runtime = XAIRuntime(application_id="tests", tenant_id="t", graph_id="echo")
    custom = LangGraphXAIEventAdapter.instrument_graph(_echo_graph(), runtime=runtime)
    assert custom.invoke({"text": "hi"}) == {"text": "HI"}
    assert custom.runtime is runtime


@tool
def lookup(item: str) -> str:
    """Look up one inventory item."""
    if item == "missing":
        raise LookupError(item)
    return f"{item}: in stock"


class LookupState(TypedDict):
    items: list[str]
    results: list[str]


def _look_up_all(state: LookupState) -> dict[str, list[str]]:
    results = []
    for item in state["items"]:
        try:
            results.append(lookup.invoke({"item": item}))
        except LookupError:
            results.append(f"{item}: unavailable")
    return {"results": results}


def _lookup_graph() -> Any:
    builder = StateGraph(LookupState)
    builder.add_node("look_up_all", _look_up_all)
    builder.add_node("summarize", lambda state: {"results": [*state["results"], "done"]})
    builder.add_edge(START, "look_up_all")
    builder.add_edge("look_up_all", "summarize")
    builder.add_edge("summarize", END)
    return builder.compile()


@pytest.fixture
def runtime() -> Iterator[XAIRuntime]:
    runtime = XAIRuntime(application_id="tests", tenant_id="t", graph_id="lookup")
    yield runtime
    runtime.run_sync(runtime.close())


def _recorded(runtime: XAIRuntime, run: Run) -> list[XAIEvent]:
    """Return the canonical events of ``run``, in recording order."""

    async def query() -> list[XAIEvent]:
        store = runtime.registry.get(ProvenanceStore)
        assert store is not None
        query = StoreFilter(application_id="tests", tenant_id="t", run_id=run.run_id)
        return [record async for record in store.query(query) if isinstance(record, XAIEvent)]

    return sorted(runtime.run_sync(query()), key=lambda record: record.sequence)


def test_recorded_provenance_drives_a_behavioral_audit(runtime: XAIRuntime) -> None:
    graph = LangGraphXAIEventAdapter.instrument_graph(_lookup_graph(), runtime=runtime)
    with runtime.collect_runs() as runs:
        result = graph.invoke({"items": ["valve", "missing", "missing"], "results": []})
    (run,) = runs
    records = _recorded(runtime, run)
    events = [ADAPTER.event(record, scope="audit") for record in records]
    engine = BehaviorEngine(
        policies=[PolicyRule("outage", "failure_streak", 2, InterventionType.ESCALATE)]
    )

    decisions = [engine.process(event) for event in events]
    replayed = [engine.process(ADAPTER.event(record, scope="audit")) for record in records]

    assert result["results"] == [
        "valve: in stock",
        "missing: unavailable",
        "missing: unavailable",
        "done",
    ]
    assert runtime.errors == ()
    tools = [(e.tool_name, e.outcome) for e in events if e.event_type is EventType.TOOL_CALL]
    assert tools == [
        ("lookup", Outcome.SUCCESS),
        ("lookup", Outcome.FAILURE),
        ("lookup", Outcome.FAILURE),
    ]
    nodes = [e.node_name for e in events if e.event_type is EventType.NODE_EXECUTION]
    assert nodes == ["look_up_all", "summarize"]
    assert [e.outcome for e in events if e.event_type is EventType.OUTCOME] == [Outcome.SUCCESS]
    for event, record in zip(events, records, strict=True):
        assert event.event_id == event.provenance_ref == str(record.id)
        assert event.run_id == str(run.run_id)
    escalations = [d for d in decisions if d.intervention.kind is InterventionType.ESCALATE]
    second_failure = [e for e in events if e.outcome is Outcome.FAILURE][1]
    assert len(escalations) == 1
    assert escalations[0].explanation is not None
    assert escalations[0].explanation.provenance_ref == second_failure.event_id
    for original, again in zip(decisions, replayed, strict=True):
        if original.actionable:
            assert again == replace(original, duplicate=True)
        else:
            assert not again.actionable


def test_a_cancelled_run_is_recorded_without_an_outcome(runtime: XAIRuntime) -> None:
    graph = LangGraphXAIEventAdapter.instrument_graph(_lookup_graph(), runtime=runtime)
    with runtime.collect_runs() as runs:
        stream = graph.stream({"items": ["valve"], "results": []})
        next(stream)
        stream.close()
    (run,) = runs

    events = [ADAPTER.event(record, scope="audit") for record in _recorded(runtime, run)]

    run_outcomes = [e for e in events if e.event_type is EventType.OUTCOME]
    assert [e.metadata["xai_event_type"] for e in run_outcomes] == ["execution.failed"]
    assert run_outcomes[0].outcome is None
