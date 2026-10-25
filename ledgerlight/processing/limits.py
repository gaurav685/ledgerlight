"""Safety limits for processing untrusted downloaded files.

Every limit here is configurable (via Settings) and tested — see
tests/test_limits.py. These are deliberately simple, synchronous checks;
the per-document *timeout* is enforced by running extraction in a worker
subprocess (ledgerlight.processing.runner), so a malformed PDF cannot hang
the whole pipeline even though the size/page/zip checks themselves are
plain Python.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path


class LimitExceededError(RuntimeError):
    """Raised by any of the checks below. Always classifies as
    error_class='limit_exceeded' in processing_attempts — see
    ledgerlight.ingestion.base.classify_exception."""


@dataclass(frozen=True)
class ProcessingLimits:
    max_file_size_bytes: int = 200_000_000
    max_pages: int = 2000
    per_document_timeout_seconds: float = 120.0
    zip_max_uncompressed_bytes: int = 1_000_000_000
    zip_max_entries: int = 10_000


def check_file_size(path: Path, limits: ProcessingLimits) -> None:
    size = path.stat().st_size
    if size > limits.max_file_size_bytes:
        raise LimitExceededError(
            f"{path}: {size} bytes > max_file_size_bytes {limits.max_file_size_bytes}"
        )


def check_page_count(page_count: int, limits: ProcessingLimits) -> None:
    if page_count > limits.max_pages:
        raise LimitExceededError(f"{page_count} pages > max_pages {limits.max_pages}")


def check_zip_safety(path: Path, limits: ProcessingLimits) -> None:
    """Rejects zip bombs (uncompressed-size / entry-count limits) and
    path-traversal entries (e.g. '../../etc/passwd' or an absolute path)
    before anything is extracted."""
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > limits.zip_max_entries:
            raise LimitExceededError(
                f"{path}: {len(infos)} entries > zip_max_entries {limits.zip_max_entries}"
            )

        total_uncompressed = 0
        for info in infos:
            name = info.filename
            if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
                raise LimitExceededError(f"{path}: path-traversal entry rejected: {name!r}")
            total_uncompressed += info.file_size
            if total_uncompressed > limits.zip_max_uncompressed_bytes:
                raise LimitExceededError(
                    f"{path}: uncompressed size exceeds zip_max_uncompressed_bytes "
                    f"{limits.zip_max_uncompressed_bytes}"
                )
