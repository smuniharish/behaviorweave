"""LangChain v1 agent middleware that applies BehaviorWeave policies to tool calls."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command

from ...engine import BehaviorEngine
from ...errors import EventValidationError
from ...events import BehaviorEvent, Outcome
from ...interventions import InterventionDecision, InterventionType

__all__ = ["BehaviorWeaveMiddleware", "default_guidance"]

type ScopeResolver = Callable[[ToolCallRequest], str]
"""Returns the behavior scope for a tool call request."""

type DecisionHook = Callable[[InterventionDecision, BehaviorEvent], None]
"""Receives every decision with the event that produced it."""

type GuidanceFormatter = Callable[[InterventionDecision], str]
"""Renders an actionable decision as text for the model."""

_ToolResult = ToolMessage | Command[Any]

# Halts are kept in memory: the least recently halted scopes are forgotten beyond this many,
# and each scope remembers this many of the tool calls whose outcomes halted it.
_MAX_HALTED_SCOPES = 10_000
_MAX_HALT_ORIGINS = 256


@dataclass(slots=True)
class _Halt:
    """Halt state of one scope."""

    decision: InterventionDecision | None = None  # None once released
    # Tool-call event IDs whose outcomes halted the scope (an insertion-ordered set). A replay
    # of one of these calls is not blocked, and once released it cannot restore the halt.
    origins: dict[str, None] = field(default_factory=dict)


def default_guidance(decision: InterventionDecision) -> str:
    """Render a decision as one instruction line, such as ``[BehaviorWeave:nudge] ...``."""
    intervention = decision.intervention
    return (
        f"[BehaviorWeave:{intervention.kind.value}] {intervention.message or intervention.reason}"
    )


class BehaviorWeaveMiddleware(AgentMiddleware):
    """Guard every tool call of a LangChain ``create_agent`` agent with BehaviorWeave.

    For each tool call the middleware:

    1. records a `tool_call` event and evaluates the engine's policies;
    2. if the decision's kind is in ``block_on``, or the scope is halted, skips the tool and
       returns an error ``ToolMessage`` containing the guidance, so the model sees why the call
       did not run;
    3. otherwise runs the tool and appends guidance for any other actionable decision to the
       tool result;
    4. if ``track_outcomes`` is enabled, records a `success` or `failure` outcome for the
       result, which drives the failure, retry, and success streak patterns. An outcome
       decision whose kind is in ``block_on`` cannot refuse the call that already ran, so it
       halts the scope: later tool calls in that scope are refused until
       [`release`][behaviorweave.integrations.langchain.BehaviorWeaveMiddleware.release] is
       called. Halts are kept in memory by this middleware instance.

    Replayed and resumed graph steps reuse their tool-call IDs, so they are recognized as
    redeliveries: the call is not counted again, and an actionable decision is repeated, so
    ``block_on`` and ``on_decision`` apply as they did the first time. The tool itself runs
    again; its outcome is a redelivery only if it repeats, and a changed outcome is recorded
    like any other. Calls whose outcomes halted a scope are not blocked by that halt when their
    step is replayed, and a redelivered outcome does not restore a halt that was released.
    LangGraph interrupts raised by a tool propagate unchanged and are not recorded as failures.

    Args:
        engine: The engine whose policies are applied.
        scope: A fixed scope, or a callable deriving one from the request. By default the
            scope is the LangGraph ``thread_id`` from the run configuration.
        block_on: Intervention kinds that prevent tool calls from running.
        track_outcomes: Whether to record tool results as `success`/`failure` outcomes.
        on_decision: Optional hook called with every decision and its event. Raise from it, or
            call LangGraph's ``interrupt()``, to stop or pause the run, for example on a
            `human_review` decision. Check ``decision.duplicate`` before repeating external
            side effects, such as paging an operator, but call ``interrupt()`` for duplicates
            too: a resumed step runs the hook again, and ``interrupt()`` returns the answer.
        formatter: Renders a decision as guidance text. Defaults to
            [`default_guidance`][behaviorweave.integrations.langchain.default_guidance].
        name: Middleware name; set it when an agent uses more than one instance.

    Example:
        ```python
        agent = create_agent(
            model,
            tools=[get_alarm],
            middleware=[BehaviorWeaveMiddleware(engine)],
        )
        agent.invoke(
            {"messages": [{"role": "user", "content": "Inspect ETCH-3"}]},
            config={"configurable": {"thread_id": "incident-42"}},
        )
        ```
    """

    def __init__(
        self,
        engine: BehaviorEngine,
        *,
        scope: str | ScopeResolver | None = None,
        block_on: Collection[InterventionType] = (InterventionType.STOP, InterventionType.PAUSE),
        track_outcomes: bool = True,
        on_decision: DecisionHook | None = None,
        formatter: GuidanceFormatter | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.scope = scope
        self.block_on = frozenset(InterventionType(kind) for kind in block_on)
        self.track_outcomes = track_outcomes
        self.on_decision = on_decision
        self.formatter: GuidanceFormatter = formatter or default_guidance
        self._name = name
        self._halts: OrderedDict[str, _Halt] = OrderedDict()
        self._halts_lock = Lock()

    @property
    def name(self) -> str:
        """Middleware name used by ``create_agent`` to tell instances apart."""
        return self._name or super().name

    def release(self, scope: str) -> bool:
        """Lift the halt on ``scope`` so that its tool calls run again.

        When ``on_decision`` paused the run with ``interrupt()``, call this from the
        application before resuming the run: the resumed tool may now succeed, in which case
        the hook does not receive the halting decision again.

        Args:
            scope: The halted scope, as resolved by the middleware.

        Returns:
            Whether the scope was halted.
        """
        with self._halts_lock:
            halt = self._halts.get(scope)
            if halt is None or halt.decision is None:
                return False
            halt.decision = None
            return True

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], _ToolResult],
    ) -> _ToolResult:
        """Evaluate policies around a synchronous tool call."""
        scope, event_id, decision, blocking = self._before(request)
        if blocking is not None:
            return self._blocked(request, blocking)
        try:
            result = handler(request)
        except GraphBubbleUp:
            raise
        except Exception:
            self._after(request, scope, event_id, failed=True)
            raise
        outcome = self._after(request, scope, event_id, failed=_is_error(result))
        return self._annotate(result, decision, outcome)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[_ToolResult]],
    ) -> _ToolResult:
        """Evaluate policies around an asynchronous tool call."""
        scope, event_id, decision, blocking = self._before(request)
        if blocking is not None:
            return self._blocked(request, blocking)
        try:
            result = await handler(request)
        except GraphBubbleUp:
            raise
        except Exception:
            self._after(request, scope, event_id, failed=True)
            raise
        outcome = self._after(request, scope, event_id, failed=_is_error(result))
        return self._annotate(result, decision, outcome)

    def _before(
        self, request: ToolCallRequest
    ) -> tuple[str, str, InterventionDecision, InterventionDecision | None]:
        scope = self._resolve_scope(request)
        event_id = _tool_event_id(request)
        call = request.tool_call
        event = BehaviorEvent.tool_call(
            call["name"], call.get("args") or {}, scope=scope, event_id=event_id
        )
        decision = self.engine.process(event)
        self._notify(decision, event)
        if decision.intervention.kind in self.block_on:
            return scope, event_id, decision, decision
        with self._halts_lock:
            halt = self._halts.get(scope)
            if halt is None or event_id in halt.origins:
                return scope, event_id, decision, None
            return scope, event_id, decision, halt.decision

    def _after(
        self, request: ToolCallRequest, scope: str, event_id: str, *, failed: bool
    ) -> InterventionDecision | None:
        if not self.track_outcomes:
            return None
        outcome = Outcome.FAILURE if failed else Outcome.SUCCESS
        event = BehaviorEvent.outcome_event(
            outcome,
            scope=scope,
            tool_name=request.tool_call["name"],
            event_id=f"{event_id}:{outcome.value}",
        )
        decision = self.engine.process(event)
        if decision.intervention.kind in self.block_on:
            self._halt(scope, decision, event_id)
        self._notify(decision, event)
        return decision

    def _halt(self, scope: str, decision: InterventionDecision, event_id: str) -> None:
        with self._halts_lock:
            halt = self._halts.get(scope)
            if halt is None:
                halt = self._halts[scope] = _Halt()
            elif decision.duplicate and halt.decision is None and event_id in halt.origins:
                return  # this call's halt was released; its redelivered outcome cannot restore it
            halt.decision = decision
            halt.origins[event_id] = None
            if len(halt.origins) > _MAX_HALT_ORIGINS:
                del halt.origins[next(iter(halt.origins))]
            self._halts.move_to_end(scope)
            if len(self._halts) > _MAX_HALTED_SCOPES:
                self._halts.popitem(last=False)

    def _notify(self, decision: InterventionDecision, event: BehaviorEvent) -> None:
        if self.on_decision is not None:
            self.on_decision(decision, event)

    def _resolve_scope(self, request: ToolCallRequest) -> str:
        if isinstance(self.scope, str):
            return self.scope
        if self.scope is not None:
            return self.scope(request)
        config = getattr(request.runtime, "config", None) or {}
        thread_id = (config.get("configurable") or {}).get("thread_id")
        if thread_id is None or thread_id == "":
            raise EventValidationError(
                "BehaviorWeaveMiddleware needs a scope: pass scope=... or invoke the agent with "
                "config={'configurable': {'thread_id': ...}}"
            )
        return str(thread_id)

    def _blocked(self, request: ToolCallRequest, decision: InterventionDecision) -> ToolMessage:
        return ToolMessage(
            content=self.formatter(decision),
            tool_call_id=request.tool_call.get("id") or "",
            name=request.tool_call.get("name"),
            status="error",
        )

    def _annotate(
        self, result: _ToolResult, *decisions: InterventionDecision | None
    ) -> _ToolResult:
        notes = [self.formatter(d) for d in decisions if d is not None and d.actionable]
        if not notes or not isinstance(result, ToolMessage):
            return result
        guidance = "\n".join(notes)
        content = result.content
        if isinstance(content, str):
            updated: str | list[Any] = f"{content}\n{guidance}" if content else guidance
        else:
            updated = [*content, {"type": "text", "text": guidance}]
        return result.model_copy(update={"content": updated})


def _tool_event_id(request: ToolCallRequest) -> str:
    call_id = request.tool_call.get("id")
    if not call_id:
        return str(uuid4())
    # Pair the call ID with the conversation length: a replayed tool step reuses both, while a
    # provider that reuses call IDs across turns still produces distinct events.
    state = request.state
    messages = state.get("messages") if isinstance(state, Mapping) else None
    if isinstance(messages, Sequence):
        return f"{call_id}@{len(messages)}"
    return call_id


def _is_error(result: _ToolResult) -> bool:
    return isinstance(result, ToolMessage) and result.status == "error"
