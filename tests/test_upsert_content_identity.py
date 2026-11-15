"""Integration regression tests: upsert_document_version must not create
a second DocumentVersion when a re-fetched single-entry ZIP (Phase 1) or
dynamic HTML page (Phase 2 preflight) has different raw bytes but
identical dedup-relevant content -- see tests/test_content_identity.py
for the pure-function versions of these tests and ADR 0004 / the Phase 2
report for the full writeup."""

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
from ledgerlight.ingestion.sources_sync import sync_sources
from ledgerlight.ingestion.upsert import upsert_document_version

pytestmark = pytest.mark.integration


def _zip_with_timestamp(
    inner_bytes: bytes, date_time: tuple[int, int, int, int, int, int]
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("bhav.csv", date_time=date_time)
        zf.writestr(info, inner_bytes)
    return buf.getvalue()


def _entry(
    url: str,
    body: bytes,
    *,
    source_id: str = "nse_archives",
    content_type: str = "application/zip",
    document_type: str = "equity_bhavcopy",
    local_path: str = "data/raw/nse_archives/2026/test.csv.zip",
) -> ManifestEntry:
    return ManifestEntry(
        record_id=str(uuid.uuid4()),
        source_id=source_id,
        source_url="https://archives.nseindia.com/",
        retrieval_url=url,
        retrieved_at=utc_now().isoformat(),
        retrieval_method="automated_fetch",
        http_status=200,
        content_type=content_type,
        bytes=len(body),
        sha256=sha256_bytes(body),
        local_path=local_path,
        document_type=document_type,
        publication_time="2023-08-21",
        licence_status="public_no_explicit_licence",
        redistribution_allowed="unclear",
    )


def test_jittered_zip_timestamp_does_not_create_a_second_version(
    db_session: Session, object_store
) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    sync_sources(db_session, repo_root / "data" / "manifests" / "sources.yaml")
    store = object_store

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


def _html_with_csrf_and_nonce_id(token: str, nav_id: str) -> bytes:
    return f"""<!DOCTYPE html><html><head><title>Example Corp</title>
<script>Liferay.authToken = '{token}';</script>
</head><body>
<nav id="{nav_id}_quickAccessNav">About Us</nav>
<p>Shareholding pattern as of Q1 2025.</p>
</body></html>""".encode()


def test_churning_html_csrf_token_does_not_create_a_second_version(
    db_session: Session, object_store
) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    sync_sources(db_session, repo_root / "data" / "manifests" / "sources.yaml")
    store = object_store

    url = f"https://www.suzlon.com/investors/test-{uuid.uuid4()}/"
    page_a = _html_with_csrf_and_nonce_id("jE6l8JTh", "cigw")
    page_b = _html_with_csrf_and_nonce_id("scNXdLRy", "pcfr")
    assert page_a != page_b  # the real-world symptom: raw bytes genuinely differ

    version1, doc_new1, ver_new1 = upsert_document_version(
        db_session,
        store,
        _entry(
            url,
            page_a,
            source_id="suzlon_ir",
            content_type="text/html",
            document_type="ir_page",
            local_path="data/raw/suzlon_ir/2026/test.html",
        ),
        page_a,
    )
    assert doc_new1 is True
    assert ver_new1 is True

    version2, doc_new2, ver_new2 = upsert_document_version(
        db_session,
        store,
        _entry(
            url,
            page_b,
            source_id="suzlon_ir",
            content_type="text/html",
            document_type="ir_page",
            local_path="data/raw/suzlon_ir/2026/test.html",
        ),
        page_b,
    )
    assert doc_new2 is False
    assert ver_new2 is False, "CSRF-token-only HTML churn must not create a spurious new version"
    assert version2.id == version1.id
