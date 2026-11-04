"""Structured logging setup (structlog), shared across Phase 0 tooling."""

from __future__ import annotations

import logging

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog to emit JSON lines to stdout at the given level.

    `merge_contextvars` must be the real FIRST processor -- without it,
    anything bound via `structlog.contextvars.bind_contextvars` (the
    real request_id/tenant_id Phase 5 §8 binds per-request) is
    silently dropped from every log line and never reaches
    `JSONRenderer` at all. Confirmed directly: before this fix, a
    real bound `request_id`/`tenant_id` never appeared in a single
    real emitted log line.

    `PrintLoggerFactory` is built with no explicit `file=` so it falls
    back to structlog's own `sys.stdout` reference bound once at
    structlog's own import time -- never passed `sys.stdout` captured
    at THIS call's own time. Confirmed directly: a caller whose own
    `sys.stdout` later gets replaced and closed (e.g. a test runner's
    output-capture fixture) left a previously-configured logger
    holding a dead file object, raising inside every subsequent real
    log call."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
