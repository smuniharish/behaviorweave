from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import uuid4


class EventType(StrEnum):
    TOOL_CALL = "tool_call"
    NODE_EXECUTION = "node_execution"
    AGENT_HANDOFF = "agent_handoff"
    DELEGATION = "delegation"
    OUTCOME = "outcome"
    RETRY = "retry"
    CUSTOM = "custom"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class BehaviorEvent:
    event_type: EventType
    scope: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid4()))
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
        if not self.scope.strip():
            raise ValueError("scope must not be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

    @classmethod
    def tool_call(
        cls,
        tool_name: str,
        arguments: Mapping[str, object] | None = None,
        *,
        scope: str,
        event_id: str | None = None,
    ) -> BehaviorEvent:
        args = dict(arguments or {})
        fingerprint = f"{tool_name}({json.dumps(args, sort_keys=True, separators=(',', ':'))})"
        return cls(
            EventType.TOOL_CALL,
            scope=scope,
            tool_name=tool_name,
            metadata={"arguments": args},
            event_id=event_id or str(uuid4()),
            fingerprint=fingerprint,
        )

    @classmethod
    def outcome_event(
        cls,
        outcome: Outcome,
        *,
        scope: str,
        event_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> BehaviorEvent:
        return cls(
            EventType.OUTCOME,
            scope=scope,
            outcome=outcome,
            event_id=event_id or str(uuid4()),
            metadata=dict(metadata or {}),
        )

    def identity(self) -> str:
        if self.event_type in {EventType.AGENT_HANDOFF, EventType.DELEGATION}:
            return f"{self.agent_name or 'unknown'}->{self.target_agent or 'unknown'}"
        raw = self.fingerprint or self.node_name or self.tool_name or self.agent_name
        return raw or self.event_type.value

    def idempotency_key(self) -> str:
        return self.event_id or sha256(self.to_json().encode()).hexdigest()

    def to_dict(self) -> dict[str, object]:
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
            "outcome": self.outcome.value if self.outcome else None,
            "metadata": dict(self.metadata),
            "provenance_ref": self.provenance_ref,
            "fingerprint": self.fingerprint,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)
