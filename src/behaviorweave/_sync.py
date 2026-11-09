"""Run BehaviorWeave coroutines from synchronous code. Not part of the public API."""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import threading
import weakref
from collections.abc import Coroutine
from typing import Any

__all__ = ["run_sync"]


class _ThreadLoop:
    """One reusable event loop per thread."""

    __slots__ = ("loop", "runner")

    def __init__(self) -> None:
        loop = asyncio.new_event_loop()
        self.loop = loop
        self.runner = asyncio.Runner(loop_factory=lambda: loop)

    def __del__(self) -> None:
        if not self.loop.is_running() and not self.loop.is_closed():
            self.loop.close()


class _HelperLoop:
    """A background event loop serving one thread whose own event loop is busy.

    A thread that already runs an event loop cannot run another one, so its calls are
    executed here. The helper stops when the calling thread releases it and closes its loop in
    its own thread.
    """

    __slots__ = ("__weakref__", "loop")

    def __init__(self) -> None:
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=_serve, args=(loop,), name="behaviorweave-sync")
        thread.daemon = True
        thread.start()
        self.loop = loop
        weakref.finalize(self, _stop, loop)

    def run[Result](
        self, coroutine: Coroutine[Any, Any, Result], context: contextvars.Context
    ) -> Result:
        # Scheduling inside `context` makes the task run with a copy of it.
        future = context.run(asyncio.run_coroutine_threadsafe, coroutine, self.loop)
        return future.result()


_local = threading.local()


def _serve(loop: asyncio.AbstractEventLoop) -> None:
    try:
        loop.run_forever()
    finally:
        loop.close()


def _stop(loop: asyncio.AbstractEventLoop) -> None:
    with contextlib.suppress(RuntimeError):  # the loop is already closed
        loop.call_soon_threadsafe(loop.stop)


def run_sync[Result](coroutine: Coroutine[Any, Any, Result]) -> Result:
    """Run ``coroutine`` to completion from synchronous code.

    Reuses one event loop per thread and runs the coroutine in a copy of the caller's
    context, so context variables (a LangGraph runnable config, an active OpenTelemetry span,
    an agxai run) propagate. When the calling thread already runs an event loop, the coroutine
    runs on a background loop that is kept for that thread and reused by later calls.
    """
    context = contextvars.copy_context()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        holder: _ThreadLoop | None = getattr(_local, "holder", None)
        if holder is None:
            holder = _local.holder = _ThreadLoop()
        return holder.runner.run(coroutine, context=context)
    helper: _HelperLoop | None = getattr(_local, "helper", None)
    if helper is None:
        helper = _local.helper = _HelperLoop()
    return helper.run(coroutine, context)
