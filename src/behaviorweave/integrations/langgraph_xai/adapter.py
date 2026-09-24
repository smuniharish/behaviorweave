from __future__ import annotations

from collections.abc import Mapping

from ...events import BehaviorEvent, EventType


class LangGraphXAIEventAdapter:
    """Consume an xAI context reference without importing private xAI modules."""

    def event(
        self, payload: Mapping[str, object], *, scope: str, provenance_ref: str | None = None
    ) -> BehaviorEvent:
        raw_type = str(payload.get("event_type", EventType.CUSTOM.value))
        try:
            event_type = EventType(raw_type)
        except ValueError:
            event_type = EventType.CUSTOM
        return BehaviorEvent(
            event_type,
            scope=scope,
            node_name=_text(payload.get("node_name")),
            tool_name=_text(payload.get("tool_name")),
            agent_name=_text(payload.get("agent_name")),
            target_agent=_text(payload.get("target_agent")),
            metadata=dict(payload),
            provenance_ref=provenance_ref,
        )

    @staticmethod
    def instrument_graph(
        graph: object,
        *,
        application_id: str = "behaviorweave",
        tenant_id: str = "default",
        graph_id: str = "graph",
    ) -> object:
        """Instrument a compiled graph through langgraph-xai's public runtime API."""
        from langgraph_xai import XAIRuntime

        runtime = XAIRuntime(application_id=application_id, tenant_id=tenant_id, graph_id=graph_id)
        return runtime.instrument(graph)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None
