"""Run an extraction function with a wall-clock timeout, in a worker
subprocess — so a malformed/adversarial PDF that hangs MuPDF cannot hang
the whole ingestion pipeline. A plain in-process `signal.alarm`-based
timeout would not help here: a true C-level hang in a native library
doesn't yield back to the Python interpreter for a signal to be delivered.

Uses multiprocessing.Process directly (not ProcessPoolExecutor) because a
hung worker must be `.terminate()`-able on timeout — ProcessPoolExecutor
blocks on shutdown waiting for in-flight work, which is exactly the hang
this module exists to avoid.

Real bug found and fixed here: `proc.join(timeout=...)` does NOT return
promptly just because the worker function has returned and queued its
result — PyMuPDF holds native (non-Python) threads that can keep the OS
process alive for many extra seconds after the Python-level work is done,
so `join()` ends up waiting out almost the entire timeout regardless of
how fast the actual extraction was. The fix is to wait on `queue.get()`
(the result is ready the moment it's queued) and only use `proc.join()`/
`terminate()` afterward, as cleanup — never as the completion signal.
"""

from __future__ import annotations

import multiprocessing as mp
import queue as queue_module
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class ProcessingTimeoutError(RuntimeError):
    pass


class ProcessingFailedError(RuntimeError):
    pass


def _worker(
    fn: Callable[..., Any], args: tuple[Any, ...], queue: mp.Queue[tuple[bool, Any]]
) -> None:
    try:
        result = fn(*args)
        queue.put((True, result))
    except Exception as exc:  # noqa: BLE001 - deliberately forwarded to the parent process
        queue.put((False, f"{exc.__class__.__name__}: {exc}"))


def run_with_timeout(fn: Callable[..., T], args: tuple[Any, ...], timeout_seconds: float) -> T:
    ctx = mp.get_context("spawn")
    result_queue: mp.Queue[tuple[bool, Any]] = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(fn, args, result_queue))
    proc.start()

    try:
        ok, payload = result_queue.get(timeout=timeout_seconds)
    except queue_module.Empty:
        proc.terminate()
        proc.join(timeout=5)
        raise ProcessingTimeoutError(
            f"{getattr(fn, '__name__', fn)} exceeded {timeout_seconds}s timeout"
        ) from None
    finally:
        # Cleanup only — never the completion signal (see module docstring).
        if proc.is_alive():
            proc.join(timeout=2)
            if proc.is_alive():
                proc.terminate()
        proc.join(timeout=5)

    if not ok:
        raise ProcessingFailedError(str(payload))
    return payload  # type: ignore[no-any-return]
