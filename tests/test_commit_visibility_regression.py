"""Regression test for the real bug found and fixed in Phase 1 (ADR 0004
§6 / docs/phase-1/phase-1-report.md §6): upsert_document_version only
called session.flush(), never session.commit(). Every live ingestion job
relied on it alone to persist new rows, so a SQLAlchemy Session's
context-manager exit (`with session_factory() as session:`) silently
ROLLED BACK every newly-fetched document the instant the script exited.

This test deliberately does NOT use the `db_session` fixture (which
wraps everything in an outer transaction rolled back at teardown -- that
pattern proves application *logic* correctness within one session, but
can never catch a missing commit(), since an uncommitted write is still
visible to a second ORM Session bound to the SAME held connection/
transaction). Instead it uses two fully independent engines/connections,
the way the real bug actually manifested: ingest with one session, close
it, then check visibility from a brand new one.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ledgerlight.acquisition.manifest import ManifestEntry
from ledgerlight.common.hashing import sha256_bytes
from ledgerlight.common.timeutil import utc_now
from ledgerlight.config.settings import Settings
from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.ingestion.sources_sync import sync_sources
from ledgerlight.ingestion.upsert import upsert_document_version
from ledgerlight.storage.s3_store import ObjectStore

pytestmark = pytest.mark.integration


def _load_real_settings() -> Settings:
    repo_root = Path(__file__).resolve().parent.parent
    return Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]


def test_ingested_rows_are_visible_from_a_brand_new_session() -> None:
    settings = _load_real_settings()
    store = ObjectStore(settings)
    repo_root = Path(__file__).resolve().parent.parent
    sources_yaml = repo_root / "data" / "manifests" / "sources.yaml"

    engine_a = create_engine(settings.database_url())
    url = (
        "https://archives.nseindia.com/content/historical/EQUITIES/"
        f"visibility-test-{uuid.uuid4()}.csv.zip"
    )
    body = (
        b"SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,"
        b"TOTALTRADES,ISIN,\n"
    )
    entry = ManifestEntry(
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
        local_path="data/raw/nse_archives/2026/visibility-test.csv.zip",
        document_type="equity_bhavcopy",
        licence_status="public_no_explicit_licence",
        redistribution_allowed="unclear",
    )

    try:
        # Session A: sync sources, ingest, then CLOSE -- simulating the
        # exact shape of the real bug (a script's `with session_factory()
        # as session:` block ending).
        with Session(bind=engine_a) as session_a:
            sync_sources(session_a, sources_yaml)
            upsert_document_version(session_a, store, entry, body)
        engine_a.dispose()

        # Session B: a fully independent engine/connection, as if a
        # completely different process queried the database afterward.
        engine_b = create_engine(settings.database_url())
        with Session(bind=engine_b) as session_b:
            document = session_b.scalar(
                select(Document).where(
                    Document.source_id == "nse_archives", Document.source_key == url
                )
            )
            assert document is not None, (
                "document is not visible from a new session/connection -- "
                "this is exactly the bug: a missing commit() made the write "
                "invisible outside the originating session"
            )
            version = session_b.scalar(
                select(DocumentVersion).where(DocumentVersion.document_id == document.id)
            )
            assert version is not None
            assert version.sha256 == entry.sha256
        engine_b.dispose()
    finally:
        # Explicit cleanup -- this test's whole point is that its writes
        # are REAL commits, so (unlike db_session-fixture tests) nothing
        # here is undone by a rollback.
        engine_c = create_engine(settings.database_url())
        with Session(bind=engine_c) as cleanup_session:
            document = cleanup_session.scalar(
                select(Document).where(
                    Document.source_id == "nse_archives", Document.source_key == url
                )
            )
            if document is not None:
                cleanup_session.query(DocumentVersion).filter(
                    DocumentVersion.document_id == document.id
                ).delete()
                cleanup_session.delete(document)
                cleanup_session.commit()
        engine_c.dispose()
