"""BehaviorWeave: deterministic behavioral policies and interventions for agent runtimes.

BehaviorWeave turns observable agent activity (tool calls, node executions, outcomes,
retries, handoffs, and delegations) into normalized events, detects behavioral patterns such
as loops, streaks, and oscillation, evaluates explicit policies, and returns a typed
intervention decision for the host runtime to apply.
"""

from .engine import AuditSink, BehaviorEngine
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
    "ConsecutivePattern",
    "EventType",
    "EventValidationError",
    "Explanation",
    "FrequencyPattern",
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
    "built_in_patterns",
]

__version__ = "1.0.0"
