"""Persists extraction output as real Event/EventField rows. Currently
wires up only AUD_RESIGN (the one real worked extractor -- see
ledgerlight.knowledge.extraction's module docstring for why the other 8
schemas aren't backed by a real extractor yet in Phase 2).

A field that fails verification is still stored (validation_status=
'failed') and a review_queue item is created -- it is never silently
dropped and never promoted as if it were trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.knowledge.extraction import (
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    extract_aud_resign_fields,
)
from ledgerlight.knowledge.models import (
    Chunk,
    Event,
    EventField,
    EventType,
    Filing,
    ReviewQueueItem,
)

DETECTOR_NAME = "aud-resign-rule-v1"
DETECTOR_VERSION = "1"


@dataclass
class ExtractionRunStats:
    chunks_processed: int = 0
    chunks_already_extracted: int = 0
    events_created: int = 0
    fields_created: int = 0
    fields_failed_verification: int = 0
    review_items_created: int = 0


def run_aud_resign_extraction(session: Session, chunk_ids: list[UUID]) -> ExtractionRunStats:
    stats = ExtractionRunStats()

    event_type = session.scalar(select(EventType).where(EventType.code == "AUD_RESIGN"))
    if event_type is None:
        raise RuntimeError("AUD_RESIGN event_type not loaded -- run `taxonomy-load` first")

    for chunk_id in chunk_ids:
        stats.chunks_processed += 1
        chunk = session.get(Chunk, chunk_id)
        if chunk is None:
            continue

        already_extracted = session.scalar(
            select(EventField.id).where(
                EventField.extractor_name == EXTRACTOR_NAME,
                EventField.extractor_version == EXTRACTOR_VERSION,
                EventField.evidence_version_id == chunk.version_id,
                EventField.evidence_page == chunk.page_number,
            )
        )
        if already_extracted is not None:
            stats.chunks_already_extracted += 1
            continue

        extracted = extract_aud_resign_fields(chunk.text, chunk.char_start)
        if not extracted:
            continue

        company_id = session.scalar(
            select(Filing.company_id).where(Filing.version_id == chunk.version_id)
        )

        overall_confidence = (
            0.9 if all(f.validation_status == "validated" for f in extracted) else 0.5
        )
        event = Event(
            event_type_id=event_type.id,
            company_id=company_id,
            event_time=None,
            published_at=None,
            known_at=chunk.known_at,
            severity="medium",
            status="needs_review"
            if any(f.validation_status != "validated" for f in extracted)
            else "candidate",
            detector_name=DETECTOR_NAME,
            detector_version=DETECTOR_VERSION,
            confidence=overall_confidence,
        )
        session.add(event)
        session.flush()
        stats.events_created += 1

        for field in extracted:
            event_field = EventField(
                event_id=event.id,
                field_name=field.field_name,
                value_json=field.value_json,
                normalized_value=field.normalized_value,
                evidence_version_id=chunk.version_id,
                evidence_page=chunk.page_number,
                evidence_char_start=field.char_start,
                evidence_char_end=field.char_end,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                confidence=0.9 if field.validation_status == "validated" else 0.3,
                validation_status=field.validation_status,
            )
            session.add(event_field)
            session.flush()
            stats.fields_created += 1

            if field.validation_status != "validated":
                stats.fields_failed_verification += 1
                session.add(
                    ReviewQueueItem(
                        item_type="event_field",
                        reference_id=event_field.id,
                        reason_code=f"evidence_{field.validation_status}",
                        priority=2,
                        status="open",
                    )
                )
                stats.review_items_created += 1

    session.commit()
    return stats
