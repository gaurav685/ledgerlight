"""Integration regression test: upsert_document_version must not create a
second DocumentVersion when a re-fetched single-entry ZIP has different
raw bytes (server-regenerated timestamp) but identical inner content --
the real bug found during Phase 1 verification (see
tests/test_content_identity.py for the pure-function version of this
test and ADR 0004 for the full writeup)."""

from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ledgerlight.acquisition.manifest import ManifestEntry
from ledgerlight.common.hashing import sha256_bytes
from ledgerlight.common.timeutil import utc_now
from ledgerlight.config.settings import Settings
from ledgerlight.ingestion.sources_sync import sync_sources
from ledgerlight.ingestion.upsert import upsert_document_version
from ledgerlight.storage.s3_store import ObjectStore

pytestmark = pytest.mark.integration


def _zip_with_timestamp(
    inner_bytes: bytes, date_time: tuple[int, int, int, int, int, int]
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("bhav.csv", date_time=date_time)
        zf.writestr(info, inner_bytes)
    return buf.getvalue()


def _entry(url: str, body: bytes) -> ManifestEntry:
    return ManifestEntry(
        record_id=str(uuid.uuid4()),
        source_id="nse_archives",
        source_url="https://archives.nseindia.com/",
        retrieval_url=url,
        retrieved_at=utc_now().isoformat(),
        retrieval_method="automated_fetch",
        http_status=200,
        content_type="application/zip",
        bytes=len(body),
        sha256=sha256_bytes(body),
        local_path="data/raw/nse_archives/2026/test.csv.zip",
        document_type="equity_bhavcopy",
        publication_time="2023-08-21",
        licence_status="public_no_explicit_licence",
        redistribution_allowed="unclear",
    )


def test_jittered_zip_timestamp_does_not_create_a_second_version(db_session: Session) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    sync_sources(db_session, repo_root / "data" / "manifests" / "sources.yaml")
    store = ObjectStore(settings)

    url = f"https://archives.nseindia.com/content/historical/EQUITIES/test-{uuid.uuid4()}.csv.zip"
    inner = b"SYMBOL,SERIES,OPEN\nINFY,EQ,1500.00\n"
    zip_a = _zip_with_timestamp(inner, (2023, 8, 21, 17, 32, 16))
    zip_b = _zip_with_timestamp(inner, (2023, 8, 21, 17, 32, 14))
    assert zip_a != zip_b  # the real-world symptom: raw bytes genuinely differ

    version1, doc_new1, ver_new1 = upsert_document_version(
        db_session, store, _entry(url, zip_a), zip_a
    )
    assert doc_new1 is True
    assert ver_new1 is True

    version2, doc_new2, ver_new2 = upsert_document_version(
        db_session, store, _entry(url, zip_b), zip_b
    )
    assert doc_new2 is False
    assert ver_new2 is False, "jittered ZIP timestamp must not create a spurious new version"
    assert version2.id == version1.id
