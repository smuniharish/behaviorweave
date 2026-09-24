from __future__ import annotations

from collections.abc import Mapping

from ...events import BehaviorEvent, EventType, Outcome


class LangChainEventAdapter:
    """Adapter for public LangChain v1 callback payloads; no monkey-patching."""

    def tool_start(
        self, tool_name: str, *, scope: str, arguments: Mapping[str, object] | None = None
    ) -> BehaviorEvent:
        return BehaviorEvent.tool_call(tool_name, arguments, scope=scope)

    def tool_error(self, *, scope: str, error_type: str) -> BehaviorEvent:
        return BehaviorEvent.outcome_event(
            Outcome.FAILURE, scope=scope, metadata={"error_type": error_type}
        )

    def retry(self, *, scope: str) -> BehaviorEvent:
        return BehaviorEvent(EventType.RETRY, scope=scope, outcome=Outcome.RETRY)
