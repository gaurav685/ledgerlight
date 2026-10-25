"""Unit tests for the per-document timeout enforcement
(ledgerlight.processing.runner.run_with_timeout) -- the real bug this
module was rewritten to fix (see its module docstring and
docs/ingestion/architecture.md) was that `proc.join(timeout=...)` doesn't
reliably detect prompt completion; these tests exercise the actual
timeout and completion paths, not just the heuristic that motivated the
rewrite.

Functions passed to run_with_timeout must be module-level (picklable for
`multiprocessing.get_context("spawn")`), hence the helpers below rather
than closures/lambdas.
"""

from __future__ import annotations

import time

import pytest

from ledgerlight.processing.runner import (
    ProcessingFailedError,
    ProcessingTimeoutError,
    run_with_timeout,
)


def _fast_add(a: int, b: int) -> int:
    return a + b


def _sleep_then_return(seconds: float) -> str:
    time.sleep(seconds)
    return "done"


def _raises_value_error() -> None:
    raise ValueError("deliberate failure for the test")


def test_fast_function_completes_and_returns_result() -> None:
    result = run_with_timeout(_fast_add, (2, 3), timeout_seconds=5.0)
    assert result == 5


def test_function_within_timeout_but_slower_than_instant_still_completes() -> None:
    # Regression check for the join()-vs-queue.get() bug: a function that
    # takes real (but well under timeout) time must return promptly, not
    # wait out most of the timeout window.
    started = time.monotonic()
    result = run_with_timeout(_sleep_then_return, (0.5,), timeout_seconds=10.0)
    elapsed = time.monotonic() - started
    assert result == "done"
    assert elapsed < 5.0, f"took {elapsed:.1f}s to return a 0.5s result under a 10s timeout"


def test_function_exceeding_timeout_raises_processing_timeout_error() -> None:
    with pytest.raises(ProcessingTimeoutError):
        run_with_timeout(_sleep_then_return, (5.0,), timeout_seconds=1.0)


def test_exception_inside_worker_is_wrapped_as_processing_failed_error() -> None:
    with pytest.raises(ProcessingFailedError):
        run_with_timeout(_raises_value_error, (), timeout_seconds=5.0)
