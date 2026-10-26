"""Full knowledge pipeline on a small, real-shaped subset: one document
version with one page of real AUD_RESIGN-shaped text, through chunking,
rule-based classification, extraction (events + fields), entity
bootstrap, and the review queue. Also verifies the whole chain is
idempotent on a second run (no duplicate events/fields/entities/mentions).

All assertions are scoped to this test's own version_id / mention span
-- the real corpus already has its own committed AUD_RESIGN events and
an audit-firm entity (see docs/knowledge/extraction.md), which the
db_session fixture's transaction can see alongside this test's own
rows, so querying globally by detector_name/entity_type would conflate
the two.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.knowledge.chunking import chunk_version
from ledgerlight.knowledge.classifier import rules_baseline_predict
from ledgerlight.knowledge.entity_bootstrap import bootstrap_audit_firm_entities
from ledgerlight.knowledge.extraction_pipeline import run_aud_resign_extraction
from ledgerlight.knowledge.models import (
    Chunk,
    Entity,
    EntityLink,
    Event,
    EventField,
    EventType,
    Mention,
)
from ledgerlight.knowledge.review_queue import summarize_queue
from ledgerlight.knowledge.taxonomy import load_taxonomy

pytestmark = pytest.mark.integration

# "KPMG" is one of the real gazetteer names the AUD_RESIGN extractor
# actually matches (ledgerlight.knowledge.extraction._KNOWN_AUDIT_FIRMS)
# -- the extractor is gazetteer-based, not generic NER, so a made-up
# firm name would exercise nothing real.
_PAGE_TEXT = (
    "UPDATE ON RESIGNATION FROM THE AUDIT ENGAGEMENT\n"
    "BY THE STATUTORY AUDITOR - KPMG\n\n"
    "This is to hereby inform that KPMG has resigned as statutory "
    "auditor with effect from April 28, 2018, due to other "
    "professional commitments."
)


def _ensure_taxonomy_loaded(session: Session) -> None:
    if session.scalar(select(EventType).where(EventType.code == "AUD_RESIGN")) is not None:
        return
    repo_root = Path(__file__).resolve().parent.parent
    load_taxonomy(session, repo_root / "data" / "taxonomy" / "taxonomy-v1.0.yaml")


def _make_document_version(session: Session) -> DocumentVersion:
    document = Document(
        source_id="sebi",
        source_key=f"test://pipeline-integration/{uuid.uuid4()}",
        document_type="announcement",
    )
    session.add(document)
    session.flush()

    body_hash = hashlib.sha256(_PAGE_TEXT.encode("utf-8")).hexdigest()
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=len(_PAGE_TEXT),
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=dt.datetime.now(dt.UTC),
        known_at=dt.datetime.now(dt.UTC),
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    session.add(version)
    session.flush()

    session.add(
        DocumentPage(
            version_id=version.id,
            page_number=1,
            raw_text=_PAGE_TEXT,
            text_sha256=body_hash,
            char_count=len(_PAGE_TEXT),
            extraction_method="text_layer",
            extractor_version="test/1",
        )
    )
    session.flush()
    return version


def _run_pipeline_once(session: Session, version: DocumentVersion) -> dict[str, int]:
    chunk_stats = chunk_version(session, version)

    chunk_ids = [
        row[0]
        for row in session.execute(
            select(Chunk.id, Chunk.text).where(Chunk.version_id == version.id)
        ).all()
        if rules_baseline_predict(row[1]) == "AUD_RESIGN"
    ]
    extraction_stats = run_aud_resign_extraction(session, chunk_ids)
    entity_stats = bootstrap_audit_firm_entities(session)

    return {
        "chunks_created": chunk_stats.chunks_created,
        "events_created": extraction_stats.events_created,
        "fields_created": extraction_stats.fields_created,
        "fields_failed_verification": extraction_stats.fields_failed_verification,
        "audit_firm_entities_created": entity_stats.audit_firm_entities_created,
        "audit_firm_links_created": entity_stats.audit_firm_links_created,
    }


def _fields_for_version(session: Session, version_id: uuid.UUID) -> list[EventField]:
    return list(
        session.scalars(
            select(EventField).where(EventField.evidence_version_id == version_id)
        ).all()
    )


def test_full_pipeline_on_small_real_subset_produces_events_fields_entities(
    db_session: Session,
) -> None:
    _ensure_taxonomy_loaded(db_session)
    version = _make_document_version(db_session)

    result = _run_pipeline_once(db_session, version)

    assert result["chunks_created"] >= 1
    assert result["events_created"] == 1
    assert result["fields_created"] == 2
    assert result["fields_failed_verification"] == 0
    assert result["audit_firm_entities_created"] == 1
    assert result["audit_firm_links_created"] == 1

    fields = _fields_for_version(db_session, version.id)
    field_names = {f.field_name for f in fields}
    assert field_names == {"audit_firm", "resignation_date"}
    for f in fields:
        assert f.validation_status == "validated"
    event_ids = {f.event_id for f in fields}
    assert len(event_ids) == 1
    event = db_session.get(Event, next(iter(event_ids)))
    assert event is not None
    assert event.status == "candidate"

    mention = db_session.scalar(select(Mention).where(Mention.version_id == version.id))
    assert mention is not None
    assert mention.surface_text == "KPMG"
    link = db_session.scalar(select(EntityLink).where(EntityLink.mention_id == mention.id))
    assert link is not None
    entity = db_session.get(Entity, link.entity_id)
    assert entity is not None
    assert entity.entity_type == "audit_firm"
    assert entity.display_name == "KPMG"

    # Nothing failed verification in this subset, so it didn't add any
    # new open review item for its own event_field rows.
    open_for_this_run = [
        item
        for item in summarize_queue(db_session).get("event_field", {}).items()
        if item[0] == "open"
    ]
    assert not open_for_this_run or open_for_this_run[0][1] == 0


def test_full_pipeline_is_idempotent_on_rerun(db_session: Session) -> None:
    _ensure_taxonomy_loaded(db_session)
    version = _make_document_version(db_session)

    first = _run_pipeline_once(db_session, version)
    second = _run_pipeline_once(db_session, version)

    assert first["events_created"] == 1
    assert second["events_created"] == 0
    assert second["fields_created"] == 0
    assert second["audit_firm_entities_created"] == 0
    assert second["audit_firm_links_created"] == 0

    fields = _fields_for_version(db_session, version.id)
    assert {f.event_id for f in fields} and len({f.event_id for f in fields}) == 1
    assert len(fields) == 2

    mentions = db_session.scalars(select(Mention).where(Mention.version_id == version.id)).all()
    assert len(mentions) == 1
