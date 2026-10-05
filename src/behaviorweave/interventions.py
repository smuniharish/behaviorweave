"""Intervention decisions, explanations, and audit records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ._util import freeze
from .events import BehaviorEvent
from .state import BehaviorState

__all__ = [
    "AuditRecord",
    "Explanation",
    "Intervention",
    "InterventionDecision",
    "InterventionType",
]


class InterventionType(StrEnum):
    """Actions BehaviorWeave can request from the host runtime.

    These are requests, not operations: BehaviorWeave never stops, pauses, or reroutes a
    graph itself. The host decides how to apply each one.
    """

    NOOP = "noop"
    """No action is needed."""
    NUDGE = "nudge"
    """Gently steer the agent, for example by appending guidance to a tool result."""
    WARNING = "warning"
    """Warn the agent or operator about undesirable behavior."""
    REDIRECT = "redirect"
    """Route execution to a different node, agent, or strategy."""
    RETRY = "retry"
    """Retry the current unit of work."""
    ESCALATE = "escalate"
    """Escalate to a supervisor agent or an operator."""
    HUMAN_REVIEW = "human_review"
    """Require a human decision before continuing."""
    FORCE_SYNTHESIS = "force_synthesis"
    """Stop gathering information and produce an answer from existing evidence."""
    PAUSE = "pause"
    """Suspend execution until it is explicitly resumed. Terminal."""
    STOP = "stop"
    """End execution. Terminal."""
    CUSTOM = "custom"
    """Application-defined action."""

    @property
    def is_terminal(self) -> bool:
        """Whether the intervention halts execution (`stop` or `pause`)."""
        return self in _TERMINAL


_TERMINAL = frozenset({InterventionType.STOP, InterventionType.PAUSE})


@dataclass(frozen=True, slots=True)
class Intervention:
    """A typed request for the host runtime.

    Attributes:
        kind: Requested action; `noop` when nothing should happen.
        message: Operator- or agent-facing instruction configured on the policy.
        reason: Deterministic explanation of why the decision was made.
        pattern: Pattern that produced the decision.
        policy: Policy that produced the decision.
        scope: Scope in which the behavior was observed.
        severity: Application-defined severity label copied from the policy.
        metadata: Additional read-only application context.
    """

    kind: InterventionType
    message: str | None = None
    reason: str = ""
    pattern: str | None = None
    policy: str | None = None
    scope: str | None = None
    severity: str = "info"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class Explanation:
    """Structured evidence for a decision.

    Attributes:
        pattern: Observed pattern ID.
        count: Pattern count when the decision was made.
        threshold: Threshold of the selected policy, or ``None`` when unavailable.
        policy: Selected policy ID, if any.
        reason: Deterministic, human-readable explanation.
        provenance_ref: Provenance reference copied from the triggering event, if any.
    """

    pattern: str
    count: int
    threshold: int | None
    policy: str | None
    reason: str
    provenance_ref: str | None = None


@dataclass(frozen=True, slots=True)
class InterventionDecision:
    """The single result returned for each processed event.

    Attributes:
        intervention: The requested action, including `noop` when no action is needed.
        explanation: Structured evidence for actionable and suppressed decisions.
        suppressed: ``True`` when an eligible policy was withheld by its cooldown or because
            a ``once_only`` policy had already fired.
        duplicate: ``True`` when the event was a redelivery of an event that a policy's pattern
            already recorded. No state changed: an actionable original decision is repeated,
            and any other comes back as a plain `noop`.
    """

    intervention: Intervention
    explanation: Explanation | None = None
    suppressed: bool = False
    duplicate: bool = False

    @property
    def actionable(self) -> bool:
        """Whether the host should act on this decision (its kind is not `noop`)."""
        return self.intervention.kind is not InterventionType.NOOP


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Immutable record of one engine decision, delivered to an engine's ``audit_sink``.

    Audit records contain observable execution data only, never model reasoning.

    Attributes:
        event: Event that was processed.
        pattern: Pattern whose observation produced the decision, if any matched.
        state: State snapshot observed by that pattern, if any.
        decision: Decision returned to the caller.
    """

    event: BehaviorEvent
    pattern: str | None
    state: BehaviorState | None
    decision: InterventionDecision
