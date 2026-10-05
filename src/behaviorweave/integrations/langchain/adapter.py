"""Build BehaviorWeave events from LangChain tool lifecycle observations."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from ...events import BehaviorEvent, EventType, Outcome

__all__ = ["LangChainEventAdapter"]


class LangChainEventAdapter:
    """Translate LangChain tool lifecycle callbacks into normalized events.

    Use it from your own callback handler or tool wrapper. It never monkey-patches LangChain
    and never evaluates policies; pass the returned events to
    [`BehaviorEngine.process`][behaviorweave.BehaviorEngine.process]. To guard a
    ``create_agent`` agent with no extra code, use
    [`BehaviorWeaveMiddleware`][behaviorweave.integrations.langchain.BehaviorWeaveMiddleware].
    """

    def tool_start(
        self,
        tool_name: str,
        *,
        scope: str,
        arguments: Mapping[str, object] | None = None,
        event_id: str | None = None,
    ) -> BehaviorEvent:
        """Return a `tool_call` event for a tool that is about to run."""
        return BehaviorEvent.tool_call(tool_name, arguments, scope=scope, event_id=event_id)

    def tool_end(
        self, *, scope: str, tool_name: str | None = None, event_id: str | None = None
    ) -> BehaviorEvent:
        """Return a `success` outcome event for a tool that completed."""
        return BehaviorEvent.outcome_event(
            Outcome.SUCCESS, scope=scope, tool_name=tool_name, event_id=event_id
        )

    def tool_error(
        self,
        *,
        scope: str,
        error_type: str,
        tool_name: str | None = None,
        event_id: str | None = None,
    ) -> BehaviorEvent:
        """Return a `failure` outcome event recording a stable error classification."""
        return BehaviorEvent.outcome_event(
            Outcome.FAILURE,
            scope=scope,
            tool_name=tool_name,
            event_id=event_id,
            metadata={"error_type": error_type},
        )

    def retry(
        self, *, scope: str, tool_name: str | None = None, event_id: str | None = None
    ) -> BehaviorEvent:
        """Return a `retry` event for a tool call that is being retried."""
        return BehaviorEvent(
            EventType.RETRY,
            scope=scope,
            event_id=event_id if event_id is not None else str(uuid4()),
            tool_name=tool_name,
            outcome=Outcome.RETRY,
        )
