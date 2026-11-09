"""Audit sinks: where the engine delivers one audit record per processed event."""

from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock

from .interventions import AuditRecord

__all__ = ["AuditSink", "InMemoryAuditSink"]


class AuditSink(ABC):
    """Base class for destinations of [`AuditRecord`][behaviorweave.AuditRecord]s.

    The engine calls `write` once per processed event, after the decision is recorded. If
    `write` raises, the exception propagates to the caller of
    [`BehaviorEngine.process`][behaviorweave.BehaviorEngine.process], and processing the same
    event again returns the same decision, so a host can retry delivery. Subclass it and
    implement `write`; override `flush` and `close` if the destination buffers records or
    holds a connection.
    """

    @abstractmethod
    async def write(self, record: AuditRecord) -> None:
        """Deliver one audit record."""

    async def flush(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Deliver any buffered records. The default does nothing."""

    async def close(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Flush and release the destination. The default does nothing."""


class InMemoryAuditSink(AuditSink):
    """Keeps every audit record in memory, in delivery order.

    Useful in tests, notebooks, and examples. Records are never evicted; use a durable sink
    in long-running services.
    """

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = Lock()

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        """Every record delivered so far, oldest first."""
        with self._lock:
            return tuple(self._records)

    async def write(self, record: AuditRecord) -> None:
        """Append ``record``."""
        with self._lock:
            self._records.append(record)

    async def clear(self) -> None:
        """Forget every record."""
        with self._lock:
            self._records.clear()
