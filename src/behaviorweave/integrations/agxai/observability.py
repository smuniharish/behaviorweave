"""Feed the events an agxai runtime captures into a BehaviorWeave engine."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from agxai import CanonicalEvent, ObservabilityProvider

from ...engine import BehaviorEngine
from ...errors import PolicyConfigurationError
from ...interventions import InterventionDecision
from .adapter import AgxaiEventAdapter

__all__ = ["BehaviorWeaveObservability", "DecisionHook", "ScopeResolver", "thread_scope"]

type ScopeResolver = Callable[[CanonicalEvent], str]
"""Return the behavior scope of a canonical event."""

type DecisionHook = Callable[[CanonicalEvent, InterventionDecision], Awaitable[None] | None]
"""Receive each decision; may be a plain function or a coroutine function."""

_BEHAVIOR_EVENT_TYPES = frozenset(
    {"node.execution", "tool.execution", "execution.completed", "execution.failed"}
)


def thread_scope(event: CanonicalEvent) -> str:
    """Scope events by conversation thread, falling back to the run ID."""
    return event.context.thread_id or str(event.context.run_id)


class BehaviorWeaveObservability(ObservabilityProvider):
    """An ``agxai.ObservabilityProvider`` that runs captured events through an engine.

    Register it as a runtime's ``observability`` provider, for example through
    [`create_agxai_runtime`][behaviorweave.integrations.agxai.create_agxai_runtime]. Node,
    tool, and run completion events are mapped by
    [`AgxaiEventAdapter`][behaviorweave.integrations.agxai.AgxaiEventAdapter] and processed;
    each decision goes to ``on_decision``. Every event, including the ones the engine ignores,
    is first forwarded to ``delegate``, so an existing exporter such as
    ``OpenTelemetryObservability`` keeps receiving the full stream.

    agxai observes; it never blocks a run on an observability provider's verdict. Apply
    decisions in the graph itself, with
    [`BehaviorWeaveMiddleware`][behaviorweave.integrations.langchain.BehaviorWeaveMiddleware],
    or act on them in ``on_decision``.

    Args:
        engine: The engine that processes the events.
        delegate: An ``agxai.ObservabilityProvider`` that also receives every event.
        scope: Resolves an event's behavior scope. Defaults to the thread ID, or the run ID
            for a run without a thread.
        on_decision: Called with each canonical event and its decision.
        adapter: The event adapter. Defaults to a new ``AgxaiEventAdapter``.

    Raises:
        PolicyConfigurationError: If ``engine`` is not a ``BehaviorEngine`` or ``delegate`` is
            not an ``agxai.ObservabilityProvider``.
    """

    def __init__(
        self,
        engine: BehaviorEngine,
        *,
        delegate: ObservabilityProvider | None = None,
        scope: ScopeResolver = thread_scope,
        on_decision: DecisionHook | None = None,
        adapter: AgxaiEventAdapter | None = None,
    ) -> None:
        if not isinstance(engine, BehaviorEngine):
            raise PolicyConfigurationError(
                f"engine must be a BehaviorEngine, not {type(engine).__name__}"
            )
        if delegate is not None and not isinstance(delegate, ObservabilityProvider):
            raise PolicyConfigurationError(
                f"delegate must be an agxai.ObservabilityProvider, not {type(delegate).__name__}"
            )
        self.engine = engine
        self.delegate = delegate
        self._scope = scope
        self._on_decision = on_decision
        self._adapter = adapter or AgxaiEventAdapter()

    async def emit(self, event: CanonicalEvent) -> None:
        """Forward ``event`` to the delegate, then process it if it describes behavior."""
        if self.delegate is not None:
            await self.delegate.emit(event)
        if event.event_type not in _BEHAVIOR_EVENT_TYPES:
            return
        behavior = self._adapter.event(event, scope=self._scope(event))
        decision = await self.engine.process(behavior)
        if self._on_decision is not None:
            result = self._on_decision(event, decision)
            if inspect.isawaitable(result):
                await result

    async def flush(self) -> None:
        """Flush the delegate and the engine's audit sink."""
        if self.delegate is not None:
            await self.delegate.flush()
        await self.engine.flush()

    async def close(self) -> None:
        """Close the delegate. The engine is left open; close it separately."""
        if self.delegate is not None:
            await self.delegate.close()
