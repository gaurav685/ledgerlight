"""Shared ingestion-job scaffolding: the BLOCKED-sources-are-unschedulable
enforcement, and the error-classification used across ingestion stages.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from ledgerlight.db.models import Source

ErrorClass = Literal[
    "network", "http_4xx", "http_5xx", "parse", "timeout", "limit_exceeded", "validation"
]


class SourceNotSchedulableError(RuntimeError):
    """Raised when code tries to ingest from a source that is not `enabled`
    in the sources table (i.e. its sources.yaml verdict is not AVAILABLE or
    AVAILABLE_WITH_LIMITS). This is the one enforcement point every
    ingestion job must go through — see tests/test_ingestion_base.py."""


def require_enabled_source(session: Session, source_id: str) -> Source:
    """The single gate every per-source ingestion job calls before doing
    any network I/O. Raises if the source is unknown or not enabled."""
    source = session.get(Source, source_id)
    if source is None:
        raise SourceNotSchedulableError(
            f"source '{source_id}' is not in the sources table — run `sources-sync` first"
        )
    if not source.enabled:
        raise SourceNotSchedulableError(
            f"source '{source_id}' has verdict {source.verdict!r} and is not enabled for "
            "ingestion — see data/manifests/sources.yaml"
        )
    return source


def classify_exception(exc: Exception) -> ErrorClass:
    """Best-effort mapping from an exception to one of the fixed error
    classes every processing_attempts row must carry. Never returns
    anything outside ErrorClass, and never swallows — the caller still
    re-raises or records the original exception/message separately."""
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return "http_4xx" if 400 <= status < 500 else "http_5xx"
    if isinstance(exc, httpx.TransportError):
        return "network"
    if isinstance(exc, TimeoutError):
        return "timeout"
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        return "validation"
    if isinstance(exc, ValueError | LookupError):
        return "parse"
    return "validation"
