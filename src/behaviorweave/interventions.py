from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from .events import BehaviorEvent
from .state import BehaviorState


class InterventionType(StrEnum):
    NOOP = "noop"
    NUDGE = "nudge"
    WARNING = "warning"
    REDIRECT = "redirect"
    RETRY = "retry"
    ESCALATE = "escalate"
    HUMAN_REVIEW = "human_review"
    FORCE_SYNTHESIS = "force_synthesis"
    PAUSE = "pause"
    STOP = "stop"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class Intervention:
    kind: InterventionType
    message: str | None = None
    reason: str = ""
    pattern: str | None = None
    policy: str | None = None
    scope: str | None = None
    severity: str = "info"
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Explanation:
    pattern: str
    count: int
    threshold: int | None
    policy: str | None
    reason: str
    provenance_ref: str | None = None


@dataclass(frozen=True, slots=True)
class InterventionDecision:
    intervention: Intervention
    explanation: Explanation | None = None
    suppressed: bool = False


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Immutable observable policy audit record; never contains chain-of-thought."""

    event: BehaviorEvent
    pattern: str | None
    state: BehaviorState | None
    decision: InterventionDecision
