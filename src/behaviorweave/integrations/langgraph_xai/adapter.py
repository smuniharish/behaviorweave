"""Translate langgraph-xai canonical events into BehaviorWeave events."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from ...errors import EventValidationError
from ...events import BehaviorEvent, EventType, Outcome

if TYPE_CHECKING:
    from langchain_core.runnables import Runnable
    from langgraph_xai import InstrumentedGraph, XAIRuntime

__all__ = ["LangGraphXAIEventAdapter"]

_XAI_EVENT_TYPES: Mapping[str, EventType] = {
    "node.execution": EventType.NODE_EXECUTION,
    "tool.execution": EventType.TOOL_CALL,
    "execution.completed": EventType.OUTCOME,
    "execution.failed": EventType.OUTCOME,
}
# Node statuses are running, completed, failed, cancelled, and interrupted; tool statuses are
# succeeded, failed, cancelled, and timed_out. Cancellations and interruptions (for example a
# human-in-the-loop pause) are neither successes nor failures, so they carry no outcome.
_STATUS_OUTCOMES: Mapping[str, Outcome] = {
    "completed": Outcome.SUCCESS,
    "succeeded": Outcome.SUCCESS,
    "failed": Outcome.FAILURE,
    "timed_out": Outcome.FAILURE,
}
# langgraph-xai reports a cancelled run as ``execution.failed`` with one of these exception types.
_CANCELLATIONS = frozenset({"CancelledError", "GeneratorExit", "KeyboardInterrupt"})


class LangGraphXAIEventAdapter:
    """Connect BehaviorWeave to `langgraph-xai` provenance through its public API only.

    [`event`][behaviorweave.integrations.langgraph_xai.LangGraphXAIEventAdapter.event] maps a
    canonical langgraph-xai event (a model or its ``model_dump()``) to a ``BehaviorEvent`` that
    keeps the canonical event ID for idempotency and as a provenance reference for explanations.
    """

    def event(
        self,
        payload: Mapping[str, object] | object,
        *,
        scope: str,
        provenance_ref: str | None = None,
    ) -> BehaviorEvent:
        """Map one canonical langgraph-xai event to a ``BehaviorEvent``.

        | langgraph-xai event type | BehaviorWeave event | Outcome |
        | --- | --- | --- |
        | `node.execution` | `node_execution` (node ID) | from the node status |
        | `tool.execution` | `tool_call` (tool name) | from the tool status |
        | `execution.completed` | `outcome` | `success` |
        | `execution.failed` | `outcome` | `failure`; none for a cancelled run |
        | BehaviorWeave event type name | that event type | explicit ``outcome`` |
        | anything else | `custom` | none |

        Node and tool statuses map as follows: `completed` and `succeeded` are successes,
        `failed` and `timed_out` are failures, and `running`, `cancelled`, and `interrupted`
        carry no outcome, so they never extend or reset a streak. The canonical ``id`` becomes
        the ``event_id``, so replayed records are deduplicated. Only a small, safe subset of the
        payload is copied into ``metadata``.

        Args:
            payload: A langgraph-xai canonical event model or a mapping with the same fields.
            scope: Non-empty behavior isolation boundary.
            provenance_ref: Explicit provenance reference. Defaults to the canonical event ID.

        Returns:
            The normalized event.

        Raises:
            EventValidationError: If ``payload`` is neither a mapping nor a Pydantic model.
        """
        data = _as_mapping(payload)
        raw_type = str(data.get("event_type") or EventType.CUSTOM.value)
        node = _mapping(data.get("node"))
        tool = _mapping(data.get("tool"))
        context = _mapping(data.get("context"))
        record_id = _ident(data.get("id"))
        metadata: dict[str, object] = {"source": "langgraph-xai", "xai_event_type": raw_type}
        sequence = data.get("sequence")
        if isinstance(sequence, int) and not isinstance(sequence, bool):
            metadata["sequence"] = sequence
        return BehaviorEvent(
            _XAI_EVENT_TYPES.get(raw_type) or _native_event_type(raw_type),
            scope=scope,
            timestamp=_timestamp(data.get("timestamp")),
            event_id=record_id or str(uuid4()),
            thread_id=_ident(context.get("thread_id")) or _ident(data.get("thread_id")),
            run_id=_ident(context.get("run_id")) or _ident(data.get("run_id")),
            node_name=_ident(node.get("node_id")) or _ident(data.get("node_name")),
            tool_name=_ident(tool.get("tool_name")) or _ident(data.get("tool_name")),
            agent_name=_ident(data.get("agent_name")),
            target_agent=_ident(data.get("target_agent")),
            outcome=_outcome(raw_type, data, node, tool),
            metadata=metadata,
            provenance_ref=provenance_ref or record_id,
        )

    @staticmethod
    def instrument_graph[Input, Output](
        graph: Runnable[Input, Output],
        *,
        runtime: XAIRuntime | None = None,
        application_id: str = "behaviorweave",
        tenant_id: str = "default",
        graph_id: str = "graph",
    ) -> InstrumentedGraph[Input, Output]:
        """Instrument a compiled graph through langgraph-xai's public ``XAIRuntime`` API.

        Args:
            graph: A compiled LangGraph graph, or any other LangChain ``Runnable``.
            runtime: Existing runtime to use. Pass your own to query its provenance store and
                close it when you are done; when omitted, a new runtime is created from the
                identifiers below and is available as the returned graph's ``runtime``.
            application_id: Logical application identifier for a new runtime.
            tenant_id: Provenance tenant identifier for a new runtime.
            graph_id: Logical graph identifier for a new runtime.

        Returns:
            The instrumented graph, invoked exactly like the original.
        """
        if runtime is None:
            from langgraph_xai import XAIRuntime

            runtime = XAIRuntime(
                application_id=application_id, tenant_id=tenant_id, graph_id=graph_id
            )
        return runtime.instrument(graph)


def _as_mapping(payload: object) -> Mapping[str, object]:
    if isinstance(payload, Mapping):
        return payload
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    raise EventValidationError(
        f"payload must be a mapping or a Pydantic model, got {type(payload).__name__}"
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _ident(value: object) -> str | None:
    if isinstance(value, UUID):
        return str(value)
    return value if isinstance(value, str) and value else None


def _native_event_type(raw_type: str) -> EventType:
    try:
        return EventType(raw_type)
    except ValueError:
        return EventType.CUSTOM


def _outcome(
    raw_type: str,
    data: Mapping[str, object],
    node: Mapping[str, object],
    tool: Mapping[str, object],
) -> Outcome | None:
    explicit = data.get("outcome")
    if isinstance(explicit, str):
        with suppress(ValueError):
            return Outcome(explicit)
    if raw_type == "execution.completed":
        return Outcome.SUCCESS
    if raw_type == "execution.failed":
        exception_type = _mapping(data.get("error")).get("exception_type")
        cancelled = isinstance(exception_type, str) and exception_type in _CANCELLATIONS
        return None if cancelled else Outcome.FAILURE
    status = node.get("status") or tool.get("status")
    return _STATUS_OUTCOMES.get(status) if isinstance(status, str) else None


def _timestamp(value: object) -> datetime:
    if isinstance(value, str):
        with suppress(ValueError):
            value = datetime.fromisoformat(value)
    if isinstance(value, datetime) and value.utcoffset() is not None:
        return value
    return datetime.now(UTC)
