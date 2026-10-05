"""Exceptions raised by BehaviorWeave.

Every exception derives from [`BehaviorWeaveError`][behaviorweave.BehaviorWeaveError], so
callers can handle all library failures with one ``except`` clause. Each concrete error also
derives from ``ValueError`` because it always reports invalid input or configuration.
"""

from __future__ import annotations

__all__ = [
    "BehaviorWeaveError",
    "EventValidationError",
    "PolicyConfigurationError",
    "StateStoreError",
]


class BehaviorWeaveError(Exception):
    """Base class for every error raised by BehaviorWeave."""


class EventValidationError(BehaviorWeaveError, ValueError):
    """Raised when a [`BehaviorEvent`][behaviorweave.BehaviorEvent] has invalid data.

    Examples include an empty ``scope``, an empty ``event_id``, a naive (timezone-unaware)
    ``timestamp``, or an unknown event type or outcome.
    """


class PolicyConfigurationError(BehaviorWeaveError, ValueError):
    """Raised when policy rules or an engine configuration are invalid.

    Examples include a non-positive threshold, duplicate policy or pattern identifiers, or a
    policy that references a pattern the engine does not provide.
    """


class StateStoreError(BehaviorWeaveError, ValueError):
    """Raised when behavior state is invalid or a state store cannot apply a transition."""
