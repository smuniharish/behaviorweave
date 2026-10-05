import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallRequest
from langchain.messages import AIMessage, ToolMessage
from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import ToolException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.types import Command, interrupt

from behaviorweave import (
    AuditRecord,
    BehaviorEngine,
    BehaviorEvent,
    EventType,
    EventValidationError,
    InterventionDecision,
    InterventionType,
    Outcome,
    PolicyRule,
)
from behaviorweave.integrations.langchain import (
    BehaviorWeaveMiddleware,
    LangChainEventAdapter,
    default_guidance,
)
from behaviorweave.integrations.langchain import middleware as middleware_module
from support import RecordingStore, ScriptedChatModel, tool_call, tool_request


def _ok(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id=request.tool_call["id"] or "")


def _engine(*rules: PolicyRule) -> tuple[BehaviorEngine, RecordingStore]:
    store = RecordingStore()
    return BehaviorEngine(policies=rules, state_store=store), store


def test_adapter_builds_normalized_events() -> None:
    adapter = LangChainEventAdapter()
    start = adapter.tool_start("get_alarm", scope="s", arguments={"m": 1}, event_id="e1")
    assert start.event_type is EventType.TOOL_CALL
    assert start.event_id == "e1"
    assert (
        start.fingerprint == BehaviorEvent.tool_call("get_alarm", {"m": 1}, scope="s").fingerprint
    )
    end = adapter.tool_end(scope="s", tool_name="get_alarm")
    assert (end.event_type, end.outcome, end.tool_name) == (
        EventType.OUTCOME,
        Outcome.SUCCESS,
        "get_alarm",
    )
    error = adapter.tool_error(scope="s", error_type="Timeout", tool_name="get_alarm")
    assert error.outcome is Outcome.FAILURE
    assert error.metadata == {"error_type": "Timeout"}
    retry = adapter.retry(scope="s", tool_name="get_alarm", event_id="r1")
    assert (retry.event_type, retry.outcome, retry.event_id) == (
        EventType.RETRY,
        Outcome.RETRY,
        "r1",
    )
    assert adapter.retry(scope="s").event_id


def test_default_guidance_prefers_the_policy_message() -> None:
    engine, _ = _engine(PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE))
    decision = engine.process(BehaviorEvent.tool_call("t", scope="s"))
    assert default_guidance(decision) == "[BehaviorWeave:nudge] 't' occurred 1 consecutive time"
    engine, _ = _engine(
        PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE, message="Reuse it.")
    )
    decision = engine.process(BehaviorEvent.tool_call("t", scope="s"))
    assert default_guidance(decision) == "[BehaviorWeave:nudge] Reuse it."


def test_middleware_annotates_blocks_and_tracks_outcomes() -> None:
    engine, store = _engine(
        PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE, message="Reuse."),
        PolicyRule("stop", "repeated_tool_call", 3, InterventionType.STOP, message="Stop."),
    )
    middleware = BehaviorWeaveMiddleware(engine)
    calls: list[str] = []

    def handler(request: ToolCallRequest) -> ToolMessage:
        calls.append(request.tool_call["id"] or "")
        return _ok(request)

    first = middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), handler)
    second = middleware.wrap_tool_call(tool_request(call_id="c2", messages=[1, 2, 3]), handler)
    third = middleware.wrap_tool_call(tool_request(call_id="c3", messages=[1, 2, 3, 4, 5]), handler)
    assert isinstance(first, ToolMessage)
    assert first.content == "ok"
    assert isinstance(second, ToolMessage)
    assert second.content == "ok\n[BehaviorWeave:nudge] Reuse."
    assert isinstance(third, ToolMessage)
    assert (third.content, third.status, third.tool_call_id) == (
        "[BehaviorWeave:stop] Stop.",
        "error",
        "c3",
    )
    assert calls == ["c1", "c2"], "blocked calls never reach the tool"
    assert store.count("thread-1", "success_streak") == 0, "success_streak has no policy"


def test_middleware_records_failures_and_reraises() -> None:
    engine, store = _engine(PolicyRule("esc", "failure_streak", 2, InterventionType.ESCALATE))
    middleware = BehaviorWeaveMiddleware(engine)

    def failing(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="boom", tool_call_id="x", status="error")

    def raising(request: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("tool crashed")

    first = middleware.wrap_tool_call(tool_request(call_id="c1"), failing)
    assert isinstance(first, ToolMessage)
    assert first.content == "boom"
    with pytest.raises(RuntimeError, match="tool crashed"):
        middleware.wrap_tool_call(tool_request(call_id="c2"), raising)
    assert store.count("thread-1", "failure_streak") == 2
    third = middleware.wrap_tool_call(tool_request(call_id="c3"), failing)
    assert isinstance(third, ToolMessage)
    assert third.content == "boom\n[BehaviorWeave:escalate] 3 consecutive failure outcomes"


def test_middleware_appends_guidance_to_content_blocks_and_skips_commands() -> None:
    engine, _ = _engine(PolicyRule("n", "repeated_tool_call", 1, InterventionType.NUDGE))
    middleware = BehaviorWeaveMiddleware(engine, track_outcomes=False)

    def blocks(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content=[{"type": "text", "text": "data"}], tool_call_id="c1")

    def empty(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="", tool_call_id="c2")

    def command(request: ToolCallRequest) -> Command[Any]:
        return Command(goto="elsewhere")

    result = middleware.wrap_tool_call(tool_request(call_id="c1"), blocks)
    assert isinstance(result, ToolMessage)
    guidance = "[BehaviorWeave:nudge] 'get_alarm' occurred 1 consecutive time"
    assert result.content[-1] == {"type": "text", "text": guidance}
    second = middleware.wrap_tool_call(tool_request(call_id="c2", args={"machine": "B"}), empty)
    assert isinstance(second, ToolMessage)
    assert isinstance(second.content, str)
    assert second.content.startswith("[BehaviorWeave:nudge]")
    goto = middleware.wrap_tool_call(tool_request(call_id="c3", args={"machine": "C"}), command)
    assert isinstance(goto, Command)


def test_middleware_scope_resolution() -> None:
    engine, store = _engine(PolicyRule("n", "repeated_tool_call", 99, InterventionType.NUDGE))
    BehaviorWeaveMiddleware(engine, scope="fixed").wrap_tool_call(tool_request(), _ok)
    BehaviorWeaveMiddleware(engine, scope=lambda r: f"tool:{r.tool_call['name']}").wrap_tool_call(
        tool_request(), _ok
    )
    BehaviorWeaveMiddleware(engine).wrap_tool_call(tool_request(thread_id="t-9"), _ok)
    assert {scope for (scope, _, _) in store.latest} == {"fixed", "tool:get_alarm", "t-9"}
    with pytest.raises(EventValidationError, match="needs a scope"):
        BehaviorWeaveMiddleware(engine).wrap_tool_call(tool_request(thread_id=None), _ok)


def test_middleware_event_ids_survive_replays() -> None:
    engine, store = _engine(PolicyRule("n", "repeated_tool_call", 99, InterventionType.NUDGE))
    middleware = BehaviorWeaveMiddleware(engine, track_outcomes=False)
    middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), _ok)
    middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), _ok)
    assert store.count("thread-1", "repeated_tool_call") == 1, "replayed step is deduplicated"
    middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1, 2, 3]), _ok)
    assert store.count("thread-1", "repeated_tool_call") == 2, "reused ID in a later turn counts"
    middleware.wrap_tool_call(tool_request(call_id=None), _ok)
    middleware.wrap_tool_call(tool_request(call_id="c9", state=object()), _ok)
    assert store.count("thread-1", "repeated_tool_call") == 4


def test_middleware_hooks_formatter_block_list_and_name() -> None:
    engine, _ = _engine(PolicyRule("warn", "repeated_tool_call", 1, InterventionType.WARNING))
    seen: list[tuple[str, EventType]] = []

    def hook(decision: InterventionDecision, event: BehaviorEvent) -> None:
        seen.append((decision.intervention.kind.value, event.event_type))

    middleware = BehaviorWeaveMiddleware(
        engine,
        block_on=["warning"],  # type: ignore[list-item]
        on_decision=hook,
        formatter=lambda d: f"custom:{d.intervention.policy}",
        name="guard",
    )
    result = middleware.wrap_tool_call(tool_request(), _ok)
    assert isinstance(result, ToolMessage)
    assert result.content == "custom:warn"
    assert seen == [("warning", EventType.TOOL_CALL)]
    assert middleware.name == "guard"
    assert BehaviorWeaveMiddleware(engine).name == "BehaviorWeaveMiddleware"


async def test_async_middleware_paths() -> None:
    engine, store = _engine(
        PolicyRule("stop", "repeated_tool_call", 3, InterventionType.STOP),
        PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
    )
    middleware = BehaviorWeaveMiddleware(engine)

    async def ok(request: ToolCallRequest) -> ToolMessage:
        return _ok(request)

    async def raising(request: ToolCallRequest) -> ToolMessage:
        raise ValueError("async failure")

    first = await middleware.awrap_tool_call(tool_request(call_id="a1"), ok)
    with pytest.raises(ValueError, match="async failure"):
        await middleware.awrap_tool_call(tool_request(call_id="a2"), raising)
    blocked = await middleware.awrap_tool_call(tool_request(call_id="a3"), ok)
    assert isinstance(first, ToolMessage)
    assert first.content == "ok"
    assert isinstance(blocked, ToolMessage)
    assert blocked.status == "error"
    assert store.count("thread-1", "repeated_tool_call") == 3


def _agent_run(invoke: Callable[..., Any]) -> list[ToolMessage]:
    result = invoke(
        {"messages": [{"role": "user", "content": "Inspect ETCH-3"}]},
        config={"configurable": {"thread_id": "incident-42"}},
    )
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]


def _guarded_agent() -> Any:
    @tool
    def get_alarm(machine: str) -> str:
        """Fetch the alarm for a machine."""
        return f"{machine}: chamber-pressure warning"

    engine = BehaviorEngine(
        policies=[
            PolicyRule("nudge", "repeated_tool_call", 2, InterventionType.NUDGE, message="Reuse."),
            PolicyRule("stop", "repeated_tool_call", 3, InterventionType.STOP, message="Stop."),
        ]
    )
    model = ScriptedChatModel(
        messages=iter(
            [
                tool_call("get_alarm", {"machine": "ETCH-3"}, "c1"),
                tool_call("get_alarm", {"machine": "ETCH-3"}, "c2"),
                tool_call("get_alarm", {"machine": "ETCH-3"}, "c3"),
                AIMessage(content="Summary: pressure warning."),
            ]
        )
    )
    return create_agent(model, [get_alarm], middleware=[BehaviorWeaveMiddleware(engine)])


def test_create_agent_integration() -> None:
    messages = _agent_run(_guarded_agent().invoke)
    assert [m.content for m in messages] == [
        "ETCH-3: chamber-pressure warning",
        "ETCH-3: chamber-pressure warning\n[BehaviorWeave:nudge] Reuse.",
        "[BehaviorWeave:stop] Stop.",
    ]
    assert [m.status for m in messages] == ["success", "success", "error"]


async def test_create_agent_async_integration() -> None:
    agent = _guarded_agent()
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Inspect ETCH-3"}]},
        config={"configurable": {"thread_id": "incident-43"}},
    )
    statuses = [m.status for m in result["messages"] if isinstance(m, ToolMessage)]
    assert statuses == ["success", "success", "error"]


def _failing(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="boom", tool_call_id=request.tool_call["id"] or "", status="error")


def test_blocking_outcome_decisions_halt_the_scope_until_released() -> None:
    engine, _ = _engine(
        PolicyRule("halt", "failure_streak", 2, InterventionType.STOP, message="Stop now.")
    )
    middleware = BehaviorWeaveMiddleware(engine)
    calls: list[str] = []

    def failing(request: ToolCallRequest) -> ToolMessage:
        calls.append(request.tool_call["id"] or "")
        return _failing(request)

    def call(call_id: str, machine: str, scope: str = "thread-1") -> ToolMessage:
        result = middleware.wrap_tool_call(
            tool_request(call_id=call_id, args={"machine": machine}, thread_id=scope), failing
        )
        assert isinstance(result, ToolMessage)
        return result

    assert call("c1", "A").content == "boom"
    assert call("c2", "B").content == "boom\n[BehaviorWeave:stop] Stop now."
    halted = call("c3", "C")
    assert (halted.content, halted.status) == ("[BehaviorWeave:stop] Stop now.", "error")
    assert call("c4", "A", scope="thread-2").content == "boom", "other scopes are unaffected"
    assert calls == ["c1", "c2", "c4"]
    assert middleware.release("thread-1")
    assert not middleware.release("thread-1")
    assert call("c5", "D").content == "boom\n[BehaviorWeave:stop] Stop now."
    assert calls == ["c1", "c2", "c4", "c5"]


def test_halts_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middleware_module, "_MAX_HALTED_SCOPES", 2)
    engine, _ = _engine(PolicyRule("halt", "failure_streak", 1, InterventionType.STOP))
    middleware = BehaviorWeaveMiddleware(engine)
    for scope in ("a", "b", "c"):
        middleware.wrap_tool_call(tool_request(thread_id=scope), _failing)
    assert not middleware.release("a"), "the oldest halt was forgotten"
    assert middleware.release("b")
    assert middleware.release("c")


def test_graph_interrupts_are_not_failures() -> None:
    engine, store = _engine(PolicyRule("outage", "failure_streak", 1, InterventionType.ESCALATE))
    middleware = BehaviorWeaveMiddleware(engine)

    def interrupted(request: ToolCallRequest) -> ToolMessage:
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        middleware.wrap_tool_call(tool_request(), interrupted)
    assert store.count("thread-1", "failure_streak") == 0


async def test_async_graph_interrupts_are_not_failures() -> None:
    engine, store = _engine(PolicyRule("outage", "failure_streak", 1, InterventionType.ESCALATE))
    middleware = BehaviorWeaveMiddleware(engine)

    async def interrupted(request: ToolCallRequest) -> ToolMessage:
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        await middleware.awrap_tool_call(tool_request(), interrupted)
    assert store.count("thread-1", "failure_streak") == 0


def test_retried_tool_calls_record_their_new_outcome() -> None:
    engine, store = _engine(PolicyRule("outage", "failure_streak", 9, InterventionType.ESCALATE))
    middleware = BehaviorWeaveMiddleware(engine)
    middleware.wrap_tool_call(tool_request(call_id="c1"), _failing)
    assert store.count("thread-1", "failure_streak") == 1
    middleware.wrap_tool_call(tool_request(call_id="c1"), _ok)
    assert store.count("thread-1", "failure_streak") == 0, "the retry's success resets the streak"


@pytest.mark.parametrize(("answer", "expected_runs"), [("reject", 1), ("approve", 2)])
def test_resumed_runs_reapply_the_original_decision(answer: str, expected_runs: int) -> None:
    runs: list[str] = []

    @tool
    def wipe(db: str) -> str:
        """Wipe a database."""
        runs.append(db)
        return f"wiped {db}"

    def require_approval(decision: InterventionDecision, event: BehaviorEvent) -> None:
        needs_review = decision.intervention.kind is InterventionType.HUMAN_REVIEW
        if needs_review and interrupt(decision.intervention.reason) != "approve":
            raise PermissionError("rejected by reviewer")

    engine, store = _engine(
        PolicyRule("review", "repeated_tool_call", 2, InterventionType.HUMAN_REVIEW)
    )
    model = ScriptedChatModel(
        messages=iter(
            [
                tool_call("wipe", {"db": "prod"}, "c1"),
                tool_call("wipe", {"db": "prod"}, "c2"),
                AIMessage(content="done"),
            ]
        )
    )
    agent = create_agent(
        model,
        [wipe],
        middleware=[BehaviorWeaveMiddleware(engine, on_decision=require_approval)],
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "ops"}}
    paused = agent.invoke({"messages": [{"role": "user", "content": "Wipe prod."}]}, config)
    assert "__interrupt__" in paused
    if answer == "reject":
        with pytest.raises(PermissionError, match="rejected by reviewer"):
            agent.invoke(Command(resume=answer), config)
    else:
        agent.invoke(Command(resume=answer), config)
    assert len(runs) == expected_runs
    assert store.count("ops", "repeated_tool_call") == 2, "the resumed call is not counted again"


def test_tools_that_interrupt_record_only_their_final_outcome() -> None:
    @tool
    def refund(order: str) -> str:
        """Refund an order after approval."""
        return f"refunded {order} ({interrupt(f'refund {order}?')})"

    engine, store = _engine(PolicyRule("outage", "failure_streak", 1, InterventionType.ESCALATE))
    model = ScriptedChatModel(
        messages=iter([tool_call("refund", {"order": "a"}, "r1"), AIMessage(content="done")])
    )
    agent = create_agent(
        model, [refund], middleware=[BehaviorWeaveMiddleware(engine)], checkpointer=InMemorySaver()
    )
    config: RunnableConfig = {"configurable": {"thread_id": "refunds"}}
    agent.invoke({"messages": [{"role": "user", "content": "Refund a."}]}, config)
    result = agent.invoke(Command(resume="yes"), config)
    contents = [m.content for m in result["messages"] if isinstance(m, ToolMessage)]
    assert contents == ["refunded a (yes)"]
    assert store.count("refunds", "failure_streak") == 0


def test_a_halting_call_is_not_blocked_by_its_own_halt_when_replayed() -> None:
    engine, _ = _engine(PolicyRule("halt", "failure_streak", 1, InterventionType.STOP))
    middleware = BehaviorWeaveMiddleware(engine)
    calls: list[str] = []

    def failing(request: ToolCallRequest) -> ToolMessage:
        calls.append(request.tool_call["id"] or "")
        return _failing(request)

    middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), failing)
    replay = middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), failing)
    other = middleware.wrap_tool_call(tool_request(call_id="c2", messages=[1, 2, 3]), failing)
    assert calls == ["c1", "c1"], "the replayed halting call runs; a new call is refused"
    assert isinstance(replay, ToolMessage)
    assert replay.content == "boom\n[BehaviorWeave:stop] 1 consecutive failure outcome"
    assert isinstance(other, ToolMessage)
    assert other.status == "error"


def test_redelivered_outcomes_do_not_halt_again_after_release() -> None:
    engine, _ = _engine(PolicyRule("halt", "failure_streak", 1, InterventionType.STOP))
    middleware = BehaviorWeaveMiddleware(engine)
    middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), _failing)
    assert middleware.release("thread-1")
    middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), _failing)
    assert not middleware.release("thread-1")


@pytest.mark.parametrize("rerun_fails", [True, False])
@pytest.mark.parametrize("release", [True, False])
def test_outcome_pauses_wait_for_the_host_to_release_the_halt(
    release: bool, rerun_fails: bool
) -> None:
    runs: list[str] = []
    answers: list[object] = []
    # The first run fails; resuming runs the tool again, which may now recover.
    failures = iter([True, rerun_fails])

    @tool
    def flaky(job: str) -> str:
        """Run one job."""
        runs.append(job)
        if next(failures, False):
            raise ToolException("boom")
        return f"{job}: done"

    flaky.handle_tool_error = True
    engine, _ = _engine(PolicyRule("pause", "failure_streak", 1, InterventionType.PAUSE))

    def pause_for_operator(decision: InterventionDecision, event: BehaviorEvent) -> None:
        if decision.intervention.kind is InterventionType.PAUSE:
            answers.append(interrupt({"reason": decision.intervention.reason}))

    middleware = BehaviorWeaveMiddleware(engine, on_decision=pause_for_operator)
    model = ScriptedChatModel(
        messages=iter(
            [
                tool_call("flaky", {"job": "a"}, "c1"),
                tool_call("flaky", {"job": "b"}, "c2"),
                AIMessage(content="done"),
            ]
        )
    )
    agent = create_agent(model, [flaky], middleware=[middleware], checkpointer=InMemorySaver())
    config: RunnableConfig = {"configurable": {"thread_id": "ops"}}
    paused = agent.invoke({"messages": [{"role": "user", "content": "Run both jobs."}]}, config)
    assert "__interrupt__" in paused
    if release:
        assert middleware.release("ops"), "the operator approved"
    result = agent.invoke(Command(resume="approved"), config)

    contents = [m.content for m in result["messages"] if isinstance(m, ToolMessage)]
    guidance = "[BehaviorWeave:pause] 1 consecutive failure outcome"
    # The resumed call runs again: a repeated failure redelivers the pause, so interrupt()
    # returns the answer without restoring a released halt; a success is recorded instead.
    assert contents[0] == (f"boom\n{guidance}" if rerun_fails else "a: done")
    assert answers == (["approved"] if rerun_fails else [])
    if release:
        assert (contents[1], runs) == ("b: done", ["a", "a", "b"])
    else:
        assert (contents[1], runs) == (guidance, ["a", "a"]), "the scope stays halted"
    assert middleware.release("ops") is not release


@pytest.mark.parametrize("once_only", [False, True])
def test_recovered_blocking_outcomes_still_halt(once_only: bool) -> None:
    failures = iter([OSError("audit backend down")])

    def flaky_sink(record: AuditRecord) -> None:
        if record.decision.intervention.kind is InterventionType.STOP:
            error = next(failures, None)
            if error is not None:
                raise error

    engine = BehaviorEngine(
        policies=[
            PolicyRule("halt", "failure_streak", 1, InterventionType.STOP, once_only=once_only)
        ],
        audit_sink=flaky_sink,
    )
    middleware = BehaviorWeaveMiddleware(engine)
    calls: list[str] = []

    def failing(request: ToolCallRequest) -> ToolMessage:
        calls.append(request.tool_call["id"] or "")
        return _failing(request)

    with pytest.raises(OSError, match="audit backend down"):
        middleware.wrap_tool_call(tool_request(call_id="a", messages=[1]), failing)
    retried = middleware.wrap_tool_call(tool_request(call_id="a", messages=[1]), failing)
    later = middleware.wrap_tool_call(tool_request(call_id="b", messages=[1, 2, 3]), failing)
    assert isinstance(retried, ToolMessage)
    assert retried.content == "boom\n[BehaviorWeave:stop] 1 consecutive failure outcome"
    assert isinstance(later, ToolMessage)
    assert later.content == "[BehaviorWeave:stop] 1 consecutive failure outcome"
    assert calls == ["a", "a"]


def test_parallel_halting_calls_are_each_exempt_on_replay() -> None:
    engine, _ = _engine(PolicyRule("pause", "failure_streak", 1, InterventionType.PAUSE))
    middleware = BehaviorWeaveMiddleware(engine)
    barrier = threading.Barrier(2)

    def parallel_failing(request: ToolCallRequest) -> ToolMessage:
        barrier.wait(timeout=5)
        return _failing(request)

    def call(call_id: str, handler: Callable[[ToolCallRequest], ToolMessage]) -> str:
        result = middleware.wrap_tool_call(tool_request(call_id=call_id, messages=[1]), handler)
        assert isinstance(result, ToolMessage)
        assert isinstance(result.content, str)
        return result.content

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda call_id: call(call_id, parallel_failing), ["c1", "c2"]))
    assert call("c1", _failing).startswith("boom"), "replayed halting calls still run"
    assert call("c2", _failing).startswith("boom")
    assert call("c3", _failing).startswith("[BehaviorWeave:pause]"), "new calls are refused"


def test_halt_origins_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middleware_module, "_MAX_HALT_ORIGINS", 1)
    engine, _ = _engine(PolicyRule("halt", "failure_streak", 1, InterventionType.STOP))
    middleware = BehaviorWeaveMiddleware(engine)
    middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), _failing)
    assert middleware.release("thread-1")
    middleware.wrap_tool_call(tool_request(call_id="c2", messages=[1, 2, 3]), _failing)
    replay = middleware.wrap_tool_call(tool_request(call_id="c1", messages=[1]), _failing)
    assert isinstance(replay, ToolMessage)
    assert replay.content == "[BehaviorWeave:stop] 2 consecutive failure outcomes", (
        "the forgotten origin is no longer exempt from the active halt"
    )
