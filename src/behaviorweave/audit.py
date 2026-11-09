"""Audit sinks: where the engine delivers one audit record per processed event."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from threading import Lock

from .errors import PolicyConfigurationError
from .interventions import AuditRecord

__all__ = ["AuditSink", "CompositeAuditSink", "InMemoryAuditSink"]


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


class CompositeAuditSink(AuditSink):
    """Delivers every audit record to several sinks, in order.

    Use it to send records to a durable store and to metrics at the same time. Each operation
    is attempted on every sink even if an earlier one fails; the first failure is raised
    afterwards. Because a retried event is delivered to every sink again, sinks should
    tolerate duplicate records (each record's decision is marked ``duplicate``).

    Args:
        sinks: The sinks to deliver to.

    Raises:
        PolicyConfigurationError: If no sink is given or an item is not an ``AuditSink``.
    """

    def __init__(self, *sinks: AuditSink) -> None:
        if not sinks:
            raise PolicyConfigurationError("CompositeAuditSink needs at least one sink")
        for sink in sinks:
            if not isinstance(sink, AuditSink):
                raise PolicyConfigurationError(
                    f"sinks must be AuditSink instances, not {type(sink).__name__}"
                )
        self.sinks: tuple[AuditSink, ...] = sinks

    async def write(self, record: AuditRecord) -> None:
        """Deliver ``record`` to every sink."""
        await self._each(lambda sink: sink.write(record))

    async def flush(self) -> None:
        """Flush every sink."""
        await self._each(lambda sink: sink.flush())

    async def close(self) -> None:
        """Close every sink."""
        await self._each(lambda sink: sink.close())

    async def _each(self, call: Callable[[AuditSink], Awaitable[None]]) -> None:
        failure: Exception | None = None
        for sink in self.sinks:
            try:
                await call(sink)
            except Exception as exc:
                failure = failure or exc
        if failure is not None:
            raise failure


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
