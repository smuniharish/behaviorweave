"""Build BehaviorWeave events from LangGraph node, tool, and multi-agent activity."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from ...events import BehaviorEvent, EventType, Outcome

__all__ = ["LangGraphEventAdapter"]


class LangGraphEventAdapter:
    """Translate LangGraph runtime observations into normalized events.

    The adapter only builds events. It never routes, interrupts, or persists anything; the
    host decides how a decision such as `stop`, `pause`, or `redirect` affects the graph.
    """

    def node(
        self,
        node_name: str,
        *,
        scope: str,
        metadata: Mapping[str, object] | None = None,
        event_id: str | None = None,
    ) -> BehaviorEvent:
        """Return a `node_execution` event for a node that is executing."""
        return BehaviorEvent(
            EventType.NODE_EXECUTION,
            scope=scope,
            event_id=_event_id(event_id),
            node_name=node_name,
            metadata=dict(metadata or {}),
        )

    def tool(
        self,
        tool_name: str,
        *,
        scope: str,
        arguments: Mapping[str, object] | None = None,
        event_id: str | None = None,
    ) -> BehaviorEvent:
        """Return a `tool_call` event for a tool invoked from a graph."""
        return BehaviorEvent.tool_call(tool_name, arguments, scope=scope, event_id=event_id)

    def outcome(
        self,
        outcome: Outcome,
        *,
        scope: str,
        node_name: str | None = None,
        event_id: str | None = None,
    ) -> BehaviorEvent:
        """Return an `outcome` event, optionally attributed to a node."""
        return BehaviorEvent.outcome_event(
            outcome, scope=scope, node_name=node_name, event_id=event_id
        )

    def handoff(
        self, source_agent: str, target_agent: str, *, scope: str, event_id: str | None = None
    ) -> BehaviorEvent:
        """Return an `agent_handoff` event for control passing between agents."""
        return BehaviorEvent(
            EventType.AGENT_HANDOFF,
            scope=scope,
            event_id=_event_id(event_id),
            agent_name=source_agent,
            target_agent=target_agent,
        )

    def delegation(
        self, source_agent: str, target_agent: str, *, scope: str, event_id: str | None = None
    ) -> BehaviorEvent:
        """Return a `delegation` event for work delegated to another agent."""
        return BehaviorEvent(
            EventType.DELEGATION,
            scope=scope,
            event_id=_event_id(event_id),
            agent_name=source_agent,
            target_agent=target_agent,
        )


def _event_id(value: str | None) -> str:
    return value if value is not None else str(uuid4())
