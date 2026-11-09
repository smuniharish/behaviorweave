from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID

import pytest
from agxai import (
    AttributionEngine,
    CanonicalEvent,
    CaptureMode,
    CapturePolicy,
    DefaultCapturePolicy,
    DefaultPolicyProvider,
    ExecutionContext,
    ExecutionStatus,
    ExplanationEngine,
    HybridAttribution,
    InMemoryProvenanceStore,
    NodeExecution,
    ObservabilityProvider,
    PolicyProvider,
    ProvenanceStore,
    Registry,
    Run,
    SemanticArtifact,
    StoreFilter,
    StructuredExplanationEngine,
    ToolExecution,
    ToolStatus,
    XAIConfig,
    XAIPlugin,
    XAIRuntime,
)
from agxai.core import (
    ExceptionEvent,
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionStartedEvent,
    NodeExecutionEvent,
    ToolExecutionEvent,
    XAIEvent,
)
from langchain.tools import tool
from langgraph.graph import END, START, StateGraph

from behaviorweave import (
    AuditRecord,
    BehaviorEngine,
    BehaviorEvent,
    EventType,
    EventValidationError,
    Explanation,
    InMemoryBehaviorStateStore,
    Intervention,
    InterventionDecision,
    InterventionType,
    Outcome,
    PolicyConfigurationError,
    PolicyRule,
)
from behaviorweave.integrations.agxai import (
    AgxaiAuditSink,
    AgxaiEventAdapter,
    BehaviorWeaveObservability,
    create_agxai_runtime,
    instrument_graph,
    thread_scope,
)
from support import at

CONTEXT = ExecutionContext(application_id="app", tenant_id="t", graph_id="g", thread_id="th-1")
ADAPTER = AgxaiEventAdapter()


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
        "source": "agxai",
        "agxai_event_type": "tool.execution",
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
    assert event.metadata["agxai_event_type"] == "execution.started"


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
        "source": "agxai",
        "agxai_event_type": "x",
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


async def test_replayed_agxai_events_are_deduplicated() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 2, InterventionType.NUDGE)]
    )
    xai_event = _tool_event(ToolStatus.SUCCEEDED)
    first = await engine.process(ADAPTER.event(xai_event, scope="s"))
    replay = await engine.process(ADAPTER.event(xai_event.model_dump(), scope="s"))
    assert not first.actionable
    assert replay.duplicate
    nudge = await engine.process(ADAPTER.event(_tool_event(ToolStatus.SUCCEEDED), scope="s"))
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


@tool
def lookup(item: str) -> str:
    """Look up one inventory item."""
    if item == "missing":
        raise LookupError(item)
    return f"{item}: in stock"


class LookupState(TypedDict):
    items: list[str]
    results: list[str]


async def _look_up_all(state: LookupState) -> dict[str, list[str]]:
    results = []
    for item in state["items"]:
        try:
            results.append(await lookup.ainvoke({"item": item}))
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
async def runtime() -> AsyncIterator[XAIRuntime]:
    runtime = create_agxai_runtime(application_id="tests", tenant_id="t", graph_id="lookup")
    yield runtime
    await runtime.close()


async def _recorded(runtime: XAIRuntime, run: Run) -> list[XAIEvent]:
    """Return the canonical events of ``run``, in recording order."""
    store = runtime.registry.get(ProvenanceStore)
    assert store is not None
    query = StoreFilter(application_id="tests", tenant_id="t", run_id=run.run_id)
    records = [record async for record in store.query(query) if isinstance(record, XAIEvent)]
    return sorted(records, key=lambda record: record.sequence)


class RecordingObservability(ObservabilityProvider):
    def __init__(self) -> None:
        self.events: list[str] = []
        self.calls: list[str] = []

    async def emit(self, event: CanonicalEvent) -> None:
        self.events.append(event.event_type)

    async def flush(self) -> None:
        self.calls.append("flush")

    async def close(self) -> None:
        self.calls.append("close")


class RecordingPlugin(XAIPlugin):
    def __init__(self) -> None:
        self.artifacts: list[SemanticArtifact] = []

    async def record(self, artifact: SemanticArtifact) -> None:
        self.artifacts.append(artifact)


async def test_create_agxai_runtime_registers_every_component() -> None:
    components: dict[type[Any], object] = {
        ProvenanceStore: InMemoryProvenanceStore(),
        ObservabilityProvider: RecordingObservability(),
        AttributionEngine: HybridAttribution(),
        ExplanationEngine: StructuredExplanationEngine(),
        PolicyProvider: DefaultPolicyProvider(),
        CapturePolicy: DefaultCapturePolicy(),
    }
    registry = Registry()
    config = XAIConfig(capture_state=CaptureMode.CUSTOM)
    runtime = create_agxai_runtime(
        config=config,
        registry=registry,
        application_id="app",
        tenant_id="tenant",
        graph_id="graph",
        plugins=[RecordingPlugin()],
        custom_state_capture=lambda before, after: dict(after),
        # pyrefly: ignore[bad-argument-type]
        store=components[ProvenanceStore],
        # pyrefly: ignore[bad-argument-type]
        observability=components[ObservabilityProvider],
        # pyrefly: ignore[bad-argument-type]
        attribution=components[AttributionEngine],
        # pyrefly: ignore[bad-argument-type]
        explanation=components[ExplanationEngine],
        # pyrefly: ignore[bad-argument-type]
        policy=components[PolicyProvider],
        # pyrefly: ignore[bad-argument-type]
        capture_policy=components[CapturePolicy],
    )
    try:
        assert runtime.config is config
        assert runtime.registry is registry
        for capability, provider in components.items():
            assert registry.get(capability) is provider
    finally:
        await runtime.close()


@pytest.mark.parametrize(
    ("keyword", "message"),
    [
        ("config", "config must be an agxai.XAIConfig, not dict"),
        ("registry", "registry must be an agxai.Registry, not dict"),
        ("store", "store must be an agxai.ProvenanceStore, not dict"),
        ("observability", "observability must be an agxai.ObservabilityProvider, not dict"),
        ("attribution", "attribution must be an agxai.AttributionEngine, not dict"),
        ("explanation", "explanation must be an agxai.ExplanationEngine, not dict"),
        ("policy", "policy must be an agxai.PolicyProvider, not dict"),
        ("capture_policy", "capture_policy must be an agxai.CapturePolicy, not dict"),
    ],
)
def test_create_agxai_runtime_rejects_foreign_components(keyword: str, message: str) -> None:
    options: dict[str, Any] = {keyword: {}}
    with pytest.raises(PolicyConfigurationError, match=message):
        create_agxai_runtime(**options)


def test_create_agxai_runtime_rejects_invalid_configuration() -> None:
    with pytest.raises(PolicyConfigurationError, match=r"plugins must be agxai\.XAIPlugin"):
        # pyrefly: ignore[bad-argument-type]
        create_agxai_runtime(plugins=[object()])
    with pytest.raises(PolicyConfigurationError, match="requires custom_state_capture"):
        create_agxai_runtime(config=XAIConfig(capture_state=CaptureMode.CUSTOM))


async def test_instrument_graph_with_default_and_custom_runtime(runtime: XAIRuntime) -> None:
    instrumented = instrument_graph(_echo_graph())
    try:
        assert await instrumented.ainvoke({"text": "ok"}) == {"text": "OK"}
        assert isinstance(instrumented.runtime, XAIRuntime)
    finally:
        await instrumented.runtime.close()
    custom = instrument_graph(_echo_graph(), runtime=runtime)
    assert await custom.ainvoke({"text": "hi"}) == {"text": "HI"}
    assert custom.runtime is runtime


async def test_recorded_provenance_drives_a_behavioral_audit(runtime: XAIRuntime) -> None:
    graph = instrument_graph(_lookup_graph(), runtime=runtime)
    with runtime.collect_runs() as runs:
        result = await graph.ainvoke({"items": ["valve", "missing", "missing"], "results": []})
    (run,) = runs
    records = await _recorded(runtime, run)
    events = [ADAPTER.event(record, scope="audit") for record in records]
    engine = BehaviorEngine(
        policies=[PolicyRule("outage", "failure_streak", 2, InterventionType.ESCALATE)]
    )

    decisions = [await engine.process(event) for event in events]
    replayed = [await engine.process(ADAPTER.event(record, scope="audit")) for record in records]

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


async def test_a_cancelled_run_is_recorded_without_an_outcome(runtime: XAIRuntime) -> None:
    graph = instrument_graph(_lookup_graph(), runtime=runtime)
    with runtime.collect_runs() as runs:
        stream = graph.astream({"items": ["valve"], "results": []})
        await anext(stream)
        await stream.aclose()
    (run,) = runs

    events = [ADAPTER.event(record, scope="audit") for record in await _recorded(runtime, run)]

    run_outcomes = [e for e in events if e.event_type is EventType.OUTCOME]
    assert [e.metadata["agxai_event_type"] for e in run_outcomes] == ["execution.failed"]
    assert run_outcomes[0].outcome is None


async def test_observability_feeds_captured_events_to_the_engine() -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("outage", "failure_streak", 2, InterventionType.ESCALATE)]
    )
    delegate = RecordingObservability()
    seen: list[tuple[str, InterventionDecision]] = []

    async def on_decision(event: CanonicalEvent, decision: InterventionDecision) -> None:
        seen.append((event.event_type, decision))

    observability = BehaviorWeaveObservability(engine, delegate=delegate, on_decision=on_decision)
    runtime = create_agxai_runtime(observability=observability)
    graph = instrument_graph(_lookup_graph(), runtime=runtime)
    try:
        await graph.ainvoke(
            {"items": ["missing", "missing"], "results": []},
            config={"configurable": {"thread_id": "inventory"}},
        )
        await runtime.flush()
    finally:
        await runtime.close()

    assert "execution.started" in delegate.events, "the delegate receives every event"
    assert {kind for kind, _ in seen} == {
        "tool.execution",
        "node.execution",
        "execution.completed",
    }
    assert len(seen) < len(delegate.events)
    escalations = [d for _, d in seen if d.intervention.kind is InterventionType.ESCALATE]
    assert len(escalations) == 1
    assert delegate.calls[-2:] == ["flush", "close"]


async def test_observability_scope_hooks_flush_and_close() -> None:
    store = InMemoryBehaviorStateStore()
    engine = BehaviorEngine(
        policies=[PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE)],
        state_store=store,
    )
    scopes: list[str] = []
    decisions: list[InterventionDecision] = []

    def scope(event: CanonicalEvent) -> str:
        scopes.append(thread_scope(event))
        return "fixed"

    observability = BehaviorWeaveObservability(
        engine, scope=scope, on_decision=lambda _, decision: decisions.append(decision)
    )
    await observability.emit(_tool_event(ToolStatus.SUCCEEDED))
    await observability.emit(ExecutionStartedEvent(context=CONTEXT, sequence=0))
    await observability.flush()
    await observability.close()
    assert scopes == ["th-1"]
    assert [d.intervention.kind for d in decisions] == [InterventionType.NUDGE]
    assert await store.delete_scope("fixed") == 1, "events are scoped by the resolver"
    threadless = replace_context(thread_id=None)
    assert thread_scope(ExecutionStartedEvent(context=threadless, sequence=0)) == str(
        threadless.run_id
    )

    silent = BehaviorWeaveObservability(engine)
    await silent.emit(_tool_event(ToolStatus.FAILED))


def replace_context(**changes: Any) -> ExecutionContext:
    return CONTEXT.model_copy(update=changes)


def test_observability_rejects_foreign_components() -> None:
    engine = BehaviorEngine()
    with pytest.raises(PolicyConfigurationError, match="engine must be a BehaviorEngine"):
        # pyrefly: ignore[bad-argument-type]
        BehaviorWeaveObservability(object())
    with pytest.raises(PolicyConfigurationError, match="delegate must be an agxai"):
        # pyrefly: ignore[bad-argument-type]
        BehaviorWeaveObservability(engine, delegate=object())


async def test_audit_sink_records_interventions_in_the_current_run(runtime: XAIRuntime) -> None:
    engine = BehaviorEngine(
        policies=[PolicyRule("reuse", "repeated_tool_call", 2, InterventionType.NUDGE)],
        audit_sink=AgxaiAuditSink(runtime),
    )
    first = BehaviorEvent.tool_call("search", {"q": "x"}, scope="s", event_id="e1")
    second = BehaviorEvent.tool_call(
        "search", {"q": "x"}, scope="s", event_id="e2", provenance_ref="prov-2"
    )

    async def agent(state: EchoState) -> EchoState:
        await engine.process(first)  # below the threshold: not recorded
        await engine.process(second)
        await engine.process(second)  # a duplicate: not recorded again
        return state

    builder = StateGraph(EchoState)
    builder.add_node("agent", agent)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    graph = instrument_graph(builder.compile(), runtime=runtime)
    with runtime.collect_runs() as runs:
        await graph.ainvoke({"text": "go"})
    (run,) = runs

    (evidence,) = run.evidence
    (decision,) = run.decisions
    assert str(evidence.evidence_type) in {"behavior_pattern", "EvidenceType.behavior_pattern"}
    assert evidence.content_reference == "prov-2"
    assert evidence.metadata["source"] == "behaviorweave"
    assert evidence.metadata["pattern"] == "repeated_tool_call"
    assert decision.selected_action == "nudge"
    assert decision.evidence_ids == [evidence.id]
    assert decision.policy_references == ["reuse"]
    assert [(f.name, f.value) for f in decision.factors] == [("count", 2), ("threshold", 2)]

    # Outside a run of the runtime, decisions are not recorded.
    third = BehaviorEvent.tool_call("search", {"q": "x"}, scope="s", event_id="e3")
    assert (await engine.process(third)).actionable
    assert len(run.decisions) == 1


def test_audit_sink_rejects_foreign_runtimes() -> None:
    with pytest.raises(PolicyConfigurationError, match=r"runtime must be an agxai\.XAIRuntime"):
        # pyrefly: ignore[bad-argument-type]
        AgxaiAuditSink(object())


async def test_audit_sink_records_decisions_without_explanations(runtime: XAIRuntime) -> None:
    sink = AgxaiAuditSink(runtime)
    event = BehaviorEvent.tool_call("search", scope="s")
    bare = InterventionDecision(Intervention(InterventionType.WARNING, reason="custom policy"))
    unbounded = InterventionDecision(
        Intervention(InterventionType.NUDGE, reason="r", pattern="p"),
        Explanation(pattern="p", count=3, threshold=None, policy=None, reason="r"),
    )

    async def agent(state: EchoState) -> EchoState:
        await sink.write(AuditRecord(event, None, None, bare))
        await sink.write(AuditRecord(event, "p", None, unbounded))
        return state

    builder = StateGraph(EchoState)
    builder.add_node("agent", agent)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    with runtime.collect_runs() as runs:
        await instrument_graph(builder.compile(), runtime=runtime).ainvoke({"text": "go"})
    (run,) = runs

    first, second = run.decisions
    assert (first.selected_action, first.factors, first.policy_references) == ("warning", [], [])
    assert "pattern" not in run.evidence[0].metadata
    assert run.evidence[0].content_reference is None
    assert [(f.name, f.value) for f in second.factors] == [("count", 3)]
