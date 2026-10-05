"""Helpers shared by the test modules."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain.agents.middleware import ToolCallRequest
from langchain.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.tool_node import ToolRuntime

from behaviorweave import BehaviorState, InMemoryBehaviorStateStore

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def at(seconds: float) -> datetime:
    """Return a timezone-aware timestamp ``seconds`` after a fixed epoch."""
    return T0 + timedelta(seconds=seconds)


class ManualClock:
    """Deterministic clock for TTL tests."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class RecordingStore(InMemoryBehaviorStateStore):
    """In-memory store that remembers the latest state written for each pattern history."""

    def __init__(self) -> None:
        super().__init__()
        self.latest: dict[tuple[str, str, str | None], BehaviorState] = {}
        self.update_calls = 0

    def update(
        self, key: str, fn: Callable[[BehaviorState | None], BehaviorState]
    ) -> BehaviorState:
        self.update_calls += 1
        state = super().update(key, fn)
        fingerprint = state.current_fingerprint if state.pattern_id == "event_frequency" else None
        self.latest[(state.scope, state.pattern_id, fingerprint)] = state
        return state

    def count(self, scope: str, pattern_id: str, fingerprint: str | None = None) -> int:
        state = self.latest.get((scope, pattern_id, fingerprint))
        return state.count if state is not None else 0


class ScriptedChatModel(GenericFakeChatModel):
    """Fake chat model that replays scripted messages and accepts tool binding."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self


def tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    """Return an AI message requesting one tool call."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def tool_request(
    *,
    call_id: str | None = "call-1",
    thread_id: str | None = "thread-1",
    messages: list[Any] | None = None,
    state: Any = None,
    args: dict[str, Any] | None = None,
) -> ToolCallRequest:
    """Return the request a LangChain agent passes to tool-call middleware."""
    config: RunnableConfig = {"configurable": {"thread_id": thread_id} if thread_id else {}}
    runtime = ToolRuntime(
        state={},
        context=None,
        config=config,
        stream_writer=lambda _chunk: None,
        tool_call_id=call_id,
        store=None,
    )
    return ToolCallRequest(
        tool_call={"name": "get_alarm", "args": args or {"machine": "ETCH-3"}, "id": call_id},
        tool=None,
        state=state if state is not None else {"messages": messages or []},
        runtime=runtime,
    )
