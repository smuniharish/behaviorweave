"""BehaviorWeave: deterministic behavioral policies and interventions for agent runtimes.

BehaviorWeave turns observable agent activity (tool calls, node executions, outcomes,
retries, handoffs, and delegations) into normalized events, detects behavioral patterns such
as loops, streaks, and oscillation, evaluates explicit policies, and returns a typed
intervention decision for the host runtime to apply.
"""

from importlib.metadata import PackageNotFoundError, version

from .audit import AuditSink, CompositeAuditSink, InMemoryAuditSink
from .engine import BehaviorEngine
from .errors import (
    BehaviorWeaveError,
    EventValidationError,
    PolicyConfigurationError,
    StateStoreError,
)
from .events import BehaviorEvent, EventType, Outcome
from .interventions import (
    AuditRecord,
    Explanation,
    Intervention,
    InterventionDecision,
    InterventionType,
)
from .patterns import (
    ConsecutivePattern,
    FrequencyPattern,
    OscillationPattern,
    Pattern,
    PatternObservation,
    StreakPattern,
    built_in_patterns,
)
from .policies import PolicyEngine, PolicyRule
from .state import BehaviorState, BehaviorStateStore, InMemoryBehaviorStateStore

__all__ = [
    "AuditRecord",
    "AuditSink",
    "BehaviorEngine",
    "BehaviorEvent",
    "BehaviorState",
    "BehaviorStateStore",
    "BehaviorWeaveError",
    "CompositeAuditSink",
    "ConsecutivePattern",
    "EventType",
    "EventValidationError",
    "Explanation",
    "FrequencyPattern",
    "InMemoryAuditSink",
    "InMemoryBehaviorStateStore",
    "Intervention",
    "InterventionDecision",
    "InterventionType",
    "OscillationPattern",
    "Outcome",
    "Pattern",
    "PatternObservation",
    "PolicyConfigurationError",
    "PolicyEngine",
    "PolicyRule",
    "StateStoreError",
    "StreakPattern",
    "__version__",
    "built_in_patterns",
]

try:
    __version__ = version("behaviorweave")
except PackageNotFoundError:  # pragma: no cover - only when imported from a source tree
    __version__ = "0.0.0"
