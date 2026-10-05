"""Normalized, immutable observations of agent runtime activity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import uuid4

from ._util import canonical, dumps, freeze
from .errors import EventValidationError

__all__ = ["BehaviorEvent", "EventType", "Outcome"]


class EventType(StrEnum):
    """Kinds of observable runtime activity."""

    TOOL_CALL = "tool_call"
    """A tool was invoked."""
    NODE_EXECUTION = "node_execution"
    """A graph node executed."""
    AGENT_HANDOFF = "agent_handoff"
    """Control passed from one agent to another."""
    DELEGATION = "delegation"
    """An agent delegated work to another agent."""
    OUTCOME = "outcome"
    """A unit of work finished with an [`Outcome`][behaviorweave.Outcome]."""
    RETRY = "retry"
    """A unit of work is being retried."""
    CUSTOM = "custom"
    """Application-defined activity."""


class Outcome(StrEnum):
    """Result classification carried by outcome and retry events."""

    SUCCESS = "success"
    """The work completed successfully."""
    FAILURE = "failure"
    """The work failed."""
    RETRY = "retry"
    """The work is being retried."""


_HANDOFF_TYPES = frozenset({EventType.AGENT_HANDOFF, EventType.DELEGATION})


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid4())


@dataclass(frozen=True, slots=True)
class BehaviorEvent:
    """An immutable, normalized observation emitted at a runtime boundary.

    String values are accepted for ``event_type`` and ``outcome`` and are converted to their
    enumerations. ``metadata`` is stored as a read-only mapping.

    Attributes:
        event_type: The kind of activity observed.
        scope: Non-empty isolation boundary for behavioral history, such as a conversation,
            thread, run, or tenant-scoped session. Events in different scopes never interact.
        timestamp: Timezone-aware time at which the activity occurred. Defaults to now (UTC).
        event_id: Unique identifier used for idempotent delivery. Reuse it only when
            redelivering the same observation. Defaults to a random UUID.
        execution_id: Optional host execution identifier.
        thread_id: Optional framework thread identifier.
        run_id: Optional framework run identifier.
        node_name: Graph node that executed, for node events.
        tool_name: Tool that was invoked, for tool events.
        agent_name: Agent that initiated a handoff or delegation.
        target_agent: Agent receiving a handoff or delegation.
        outcome: Result classification for outcome and retry events.
        metadata: JSON-compatible application context. Never place secrets or private model
            reasoning here.
        provenance_ref: Opaque reference to external provenance or explainability records.
        fingerprint: Optional application-defined identity used for pattern comparison. When
            set, it takes precedence over every derived identity.

    Raises:
        EventValidationError: If ``scope`` or ``event_id`` is empty, ``timestamp`` is naive,
            or ``event_type``/``outcome`` is not a known value.
    """

    event_type: EventType
    scope: str
    timestamp: datetime = field(default_factory=_now)
    event_id: str = field(default_factory=_new_id)
    execution_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None
    node_name: str | None = None
    tool_name: str | None = None
    agent_name: str | None = None
    target_agent: str | None = None
    outcome: Outcome | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    provenance_ref: str | None = None
    fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", _coerce(EventType, self.event_type, "event_type"))
        if self.outcome is not None:
            object.__setattr__(self, "outcome", _coerce(Outcome, self.outcome, "outcome"))
        if not isinstance(self.scope, str) or not self.scope.strip():
            raise EventValidationError("scope must be a non-empty string")
        if not isinstance(self.event_id, str) or not self.event_id:
            raise EventValidationError("event_id must be a non-empty string")
        if not isinstance(self.timestamp, datetime) or self.timestamp.utcoffset() is None:
            raise EventValidationError("timestamp must be a timezone-aware datetime")
        object.__setattr__(self, "metadata", freeze(self.metadata))

    @classmethod
    def tool_call(
        cls,
        tool_name: str,
        arguments: Mapping[str, object] | None = None,
        *,
        scope: str,
        event_id: str | None = None,
        timestamp: datetime | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
        provenance_ref: str | None = None,
    ) -> BehaviorEvent:
        """Create a `tool_call` event with a deterministic argument fingerprint.

        The fingerprint combines the tool name with a SHA-256 digest of the canonical
        arguments, so equivalent mappings match regardless of key order, arbitrary argument
        values never fail to fingerprint, and raw argument values are not used as identities.

        Args:
            tool_name: Name of the invoked tool.
            arguments: Tool arguments. They are also recorded as ``metadata["arguments"]``.
            scope: Non-empty behavior isolation boundary.
            event_id: Stable identifier for idempotent delivery; a UUID when omitted.
            timestamp: Timezone-aware event time; now (UTC) when omitted.
            thread_id: Optional framework thread identifier.
            run_id: Optional framework run identifier.
            metadata: Additional context merged with the recorded arguments.
            provenance_ref: Optional opaque provenance reference.

        Returns:
            The normalized tool-call event.

        Raises:
            EventValidationError: If ``tool_name`` is empty or another field is invalid.
        """
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise EventValidationError("tool_name must be a non-empty string")
        args = dict(arguments or {})
        return cls(
            EventType.TOOL_CALL,
            scope=scope,
            timestamp=timestamp if timestamp is not None else _now(),
            event_id=event_id if event_id is not None else _new_id(),
            thread_id=thread_id,
            run_id=run_id,
            tool_name=tool_name,
            metadata={**(metadata or {}), "arguments": args},
            provenance_ref=provenance_ref,
            fingerprint=_tool_fingerprint(tool_name, args),
        )

    @classmethod
    def outcome_event(
        cls,
        outcome: Outcome,
        *,
        scope: str,
        event_id: str | None = None,
        timestamp: datetime | None = None,
        tool_name: str | None = None,
        node_name: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
        provenance_ref: str | None = None,
    ) -> BehaviorEvent:
        """Create an `outcome` event.

        Args:
            outcome: `success`, `failure`, or `retry`.
            scope: Non-empty behavior isolation boundary.
            event_id: Stable identifier for idempotent delivery; a UUID when omitted.
            timestamp: Timezone-aware event time; now (UTC) when omitted.
            tool_name: Optional tool that produced the outcome.
            node_name: Optional graph node that produced the outcome.
            thread_id: Optional framework thread identifier.
            run_id: Optional framework run identifier.
            metadata: Optional context associated with the outcome.
            provenance_ref: Optional opaque provenance reference.

        Returns:
            The normalized outcome event.
        """
        return cls(
            EventType.OUTCOME,
            scope=scope,
            timestamp=timestamp if timestamp is not None else _now(),
            event_id=event_id if event_id is not None else _new_id(),
            thread_id=thread_id,
            run_id=run_id,
            node_name=node_name,
            tool_name=tool_name,
            outcome=outcome,
            metadata=dict(metadata or {}),
            provenance_ref=provenance_ref,
        )

    def identity(self) -> str:
        """Return the identity that patterns compare between events.

        Precedence: an explicit ``fingerprint``; ``agent_name->target_agent`` for handoffs and
        delegations; otherwise the node, tool, or agent name. Outcome events append their
        outcome (for example ``"failure"`` or ``"fetch:failure"``). Events without any name
        fall back to their event type.
        """
        if self.fingerprint:
            return self.fingerprint
        if self.event_type in _HANDOFF_TYPES:
            return f"{self.agent_name or 'unknown'}->{self.target_agent or 'unknown'}"
        subject = self.node_name or self.tool_name or self.agent_name
        if self.event_type is EventType.OUTCOME and self.outcome is not None:
            return f"{subject}:{self.outcome.value}" if subject else self.outcome.value
        return subject or self.event_type.value

    def idempotency_key(self) -> str:
        """Return the key used to deduplicate redelivered events (the ``event_id``)."""
        return self.event_id

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dictionary representation of the event."""
        return {
            "event_type": self.event_type.value,
            "scope": self.scope,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "execution_id": self.execution_id,
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "node_name": self.node_name,
            "tool_name": self.tool_name,
            "agent_name": self.agent_name,
            "target_agent": self.target_agent,
            "outcome": self.outcome.value if self.outcome is not None else None,
            "metadata": canonical(self.metadata),
            "provenance_ref": self.provenance_ref,
            "fingerprint": self.fingerprint,
        }

    def to_json(self) -> str:
        """Return a stable, key-sorted JSON representation of the event."""
        return json.dumps(self.to_dict(), sort_keys=True)


def _coerce[E: StrEnum](enum: type[E], value: object, name: str) -> E:
    if isinstance(value, enum):
        return value
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum)
        raise EventValidationError(f"{name} must be one of: {allowed}; got {value!r}") from None


def _tool_fingerprint(tool_name: str, arguments: Mapping[str, object]) -> str:
    digest = sha256(dumps(canonical(arguments)).encode()).hexdigest()
    return f"{tool_name}#{digest[:32]}"
