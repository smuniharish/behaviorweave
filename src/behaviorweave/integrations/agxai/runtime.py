"""Build and use agxai runtimes with any of their components replaced."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from agxai import (
    AttributionEngine,
    CapturePolicy,
    ExplanationEngine,
    ObservabilityProvider,
    PolicyProvider,
    ProvenanceStore,
    Registry,
    XAIConfig,
    XAIPlugin,
    XAIRuntime,
)

from ...errors import PolicyConfigurationError

if TYPE_CHECKING:
    from agxai.integrations.langgraph import InstrumentedGraph
    from langchain_core.runnables import Runnable

__all__ = ["create_agxai_runtime", "instrument_graph"]


def create_agxai_runtime(
    *,
    config: XAIConfig | None = None,
    registry: Registry | None = None,
    application_id: str = "behaviorweave",
    tenant_id: str = "default",
    graph_id: str = "graph",
    plugins: Sequence[XAIPlugin] = (),
    custom_state_capture: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
    | None = None,
    store: ProvenanceStore | None = None,
    observability: ObservabilityProvider | None = None,
    attribution: AttributionEngine | None = None,
    explanation: ExplanationEngine | None = None,
    policy: PolicyProvider | None = None,
    capture_policy: CapturePolicy | None = None,
) -> XAIRuntime:
    """Build an ``agxai.XAIRuntime`` with any of its components replaced.

    Every agxai extension point can be supplied here: the runtime settings and identity,
    plugins, custom state capture, and each registered capability. A capability left as
    ``None`` keeps the provider already in ``registry``, or agxai's default. Instrument graphs
    with the returned runtime through
    [`instrument_graph`][behaviorweave.integrations.agxai.instrument_graph], record
    interventions with [`AgxaiAuditSink`][behaviorweave.integrations.agxai.AgxaiAuditSink], and
    feed captured events to an engine with
    [`BehaviorWeaveObservability`][behaviorweave.integrations.agxai.BehaviorWeaveObservability].

    Args:
        config: ``agxai.XAIConfig`` capture, failure, and concurrency settings.
        registry: An ``agxai.Registry`` to share providers between runtimes.
        application_id: Default application identifier of recorded runs.
        tenant_id: Default tenant identifier of recorded runs.
        graph_id: Default graph identifier of recorded runs.
        plugins: ``agxai.XAIPlugin`` instances that receive semantic artifacts.
        custom_state_capture: The state capture function agxai requires for
            ``CaptureMode.CUSTOM``.
        store: The ``agxai.ProvenanceStore`` that records executions.
        observability: The ``agxai.ObservabilityProvider`` canonical events go to, such as
            ``OpenTelemetryObservability``, ``LangSmithObservability``,
            ``LangfuseObservability``, or a ``BehaviorWeaveObservability``.
        attribution: The ``agxai.AttributionEngine`` that scores decisions.
        explanation: The ``agxai.ExplanationEngine`` that renders explanations.
        policy: The ``agxai.PolicyProvider`` that filters explanations by audience.
        capture_policy: The ``agxai.CapturePolicy`` that gates captured events.

    Returns:
        The configured runtime. Close it with ``await runtime.close()`` when you are done.

    Raises:
        PolicyConfigurationError: If a setting, component, or plugin is not an instance of its
            agxai type, or agxai rejects the configuration.
    """
    settings: tuple[tuple[str, type[Any], object | None], ...] = (
        ("config", XAIConfig, config),
        ("registry", Registry, registry),
    )
    capabilities: tuple[tuple[str, type[Any], object | None], ...] = (
        ("store", ProvenanceStore, store),
        ("observability", ObservabilityProvider, observability),
        ("attribution", AttributionEngine, attribution),
        ("explanation", ExplanationEngine, explanation),
        ("policy", PolicyProvider, policy),
        ("capture_policy", CapturePolicy, capture_policy),
    )
    for name, kind, value in (*settings, *capabilities):
        if value is not None and not isinstance(value, kind):
            raise PolicyConfigurationError(
                f"{name} must be an agxai.{kind.__name__}, not {type(value).__name__}"
            )
    for plugin in plugins:
        if not isinstance(plugin, XAIPlugin):
            raise PolicyConfigurationError(
                f"plugins must be agxai.XAIPlugin instances, not {type(plugin).__name__}"
            )
    try:
        runtime = XAIRuntime(
            config,
            registry,
            application_id=application_id,
            tenant_id=tenant_id,
            graph_id=graph_id,
            plugins=tuple(plugins),
            custom_state_capture=custom_state_capture,
        )
    except ValueError as error:
        raise PolicyConfigurationError(str(error)) from error
    for _, capability, provider in capabilities:
        if provider is not None:
            runtime.register(capability, provider)
    return runtime


def instrument_graph[Input, Output](
    graph: Runnable[Input, Output],
    *,
    runtime: XAIRuntime | None = None,
) -> InstrumentedGraph[Input, Output]:
    """Instrument a compiled graph through agxai's public ``XAIRuntime.instrument`` API.

    Args:
        graph: A compiled LangGraph graph, or any other LangChain ``Runnable``.
        runtime: The runtime that captures the graph's runs. Build one with
            [`create_agxai_runtime`][behaviorweave.integrations.agxai.create_agxai_runtime] to
            choose its store, exporters, and other components. When omitted, a runtime with
            agxai's defaults is created; it is available as the returned graph's ``runtime``.

    Returns:
        The instrumented graph, invoked exactly like the original.
    """
    if runtime is None:
        runtime = create_agxai_runtime()
    return runtime.instrument(graph)
