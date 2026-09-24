from __future__ import annotations

from collections.abc import Mapping

from ...events import BehaviorEvent, EventType, Outcome


class LangGraphEventAdapter:
    """Translate public callback/runtime payloads into normalized events."""

    def node(
        self, node_name: str, *, scope: str, metadata: Mapping[str, object] | None = None
    ) -> BehaviorEvent:
        return BehaviorEvent(
            EventType.NODE_EXECUTION,
            scope=scope,
            node_name=node_name,
            metadata=dict(metadata or {}),
        )

    def tool(
        self, tool_name: str, *, scope: str, arguments: Mapping[str, object] | None = None
    ) -> BehaviorEvent:
        return BehaviorEvent.tool_call(tool_name, arguments, scope=scope)

    def outcome(self, outcome: Outcome, *, scope: str) -> BehaviorEvent:
        return BehaviorEvent.outcome_event(outcome, scope=scope)
