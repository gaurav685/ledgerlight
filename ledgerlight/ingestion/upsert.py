"""Shared Document/DocumentVersion upsert logic for one manifest entry.

Used by both store-backfill (batch, over Phase 0's manifests) and every
live per-source ingestion job (one entry at a time, right after a fetch)
— one code path for "never overwrite, create a new version only for
genuinely new content", so the two can't drift apart.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.acquisition.manifest import ManifestEntry
from ledgerlight.db.models import Document, DocumentVersion
from ledgerlight.db.temporal import compute_known_at
from ledgerlight.ingestion.date_parsing import parse_publication_time
from ledgerlight.processing.mime_sniff import sniff_mime
from ledgerlight.storage.s3_store import ObjectStore


def upsert_document_version(
    session: Session, store: ObjectStore, entry: ManifestEntry, body: bytes
) -> tuple[DocumentVersion, bool, bool]:
    """Returns (version, document_was_new, version_was_new).

    `body` is passed in (rather than re-read from entry.local_path) so
    live ingestion jobs that already have the bytes in memory don't need
    a disk round-trip; store-backfill reads the file itself and passes
    the bytes through.
    """
    ext = Path(entry.local_path).suffix
    object_key, _object_was_new = store.put_content_addressed(body, entry.sha256, ext)
    mime = entry.content_type.split(";")[0].strip() if entry.content_type else sniff_mime(body)

    document = session.scalar(
        select(Document).where(
            Document.source_id == entry.source_id, Document.source_key == entry.retrieval_url
        )
    )
    document_was_new = False
    if document is None:
        company = entry.company_identifiers
        document = Document(
            source_id=entry.source_id,
            source_key=entry.retrieval_url,
            bse_code=company.bse_scrip_code if company else None,
            nse_symbol=company.nse_symbol if company else None,
            isin=company.isin if company else None,
            document_type=entry.document_type,
        )
        session.add(document)
        session.flush()
        document_was_new = True

    existing_version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id, DocumentVersion.sha256 == entry.sha256
        )
    )
    if existing_version is not None:
        session.commit()
        return existing_version, document_was_new, False

    retrieved_at = dt.datetime.fromisoformat(entry.retrieved_at)
    published_at = parse_publication_time(entry.publication_time)
    known_at, known_at_basis = compute_known_at(
        source_id=entry.source_id,
        published_at=published_at,
        snapshot_at=None,
        retrieved_at=retrieved_at,
    )

    version = DocumentVersion(
        document_id=document.id,
        sha256=entry.sha256,
        object_key=object_key,
        bytes=entry.bytes,
        mime_type=mime,
        retrieval_method=entry.retrieval_method,
        retrieval_url=entry.retrieval_url,
        http_status=entry.http_status,
        retrieved_at=retrieved_at,
        published_at=published_at,
        snapshot_at=None,
        known_at=known_at,
        known_at_basis=known_at_basis,
        tool_version=entry.tool_version,
    )
    session.add(version)
    session.commit()
    return version, document_was_new, True
