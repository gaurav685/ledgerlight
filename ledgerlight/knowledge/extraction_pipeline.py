"""Persists extraction output as real Event/EventField rows. Currently
wires up only AUD_RESIGN (the one real worked extractor -- see
ledgerlight.knowledge.extraction's module docstring for why the other 8
schemas aren't backed by a real extractor yet in Phase 2).

A field that fails verification is still stored (validation_status=
'failed') and a review_queue item is created -- it is never silently
dropped and never promoted as if it were trustworthy.

DETECTOR_VERSION 2 (Phase 3 §1.4): a real, gold-confirmed false positive
was found in the v1 output -- an event existed with *only* a
`resignation_date` field and no `audit_firm` field at all, because v1's
gate was `if not extracted: continue` (any non-empty field list,
including just a lone date, created an event). That event's source
chunk is a KMP-roster-table row ("Ms. Janhavi Khele - Company Secretary
(Resigned w.e.f. April 18, 2025)") that gold review explicitly corrected
away from AUD_RESIGN to KMP_EXIT -- i.e. this wasn't a near-miss, it was
a demonstrated wrong event, not a statistical estimate. v2 requires
`audit_firm` to be among the extracted fields before creating an event
at all. The old v1 event is NOT deleted (immutability) but is flagged
via a review_queue item; new v2 events set `supersedes_event_id` to any
pre-existing event for the same (version, page) so the correction is
traceable rather than silent.
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
DETECTOR_VERSION = "2"
REQUIRED_FIELD_NAMES = frozenset({"audit_firm"})


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
        if not REQUIRED_FIELD_NAMES.issubset({f.field_name for f in extracted}):
            # A lone date (or any field set missing audit_firm) is not
            # enough evidence for a real AUD_RESIGN event -- see this
            # module's docstring for the real false positive this gate
            # was added to prevent recurring.
            continue

        company_id = session.scalar(
            select(Filing.company_id).where(Filing.version_id == chunk.version_id)
        )

        # If an earlier-version event already exists for this exact
        # (version, page), the new event supersedes it -- traceable,
        # not silent, and the old row is never deleted or overwritten.
        superseded_event_id = session.scalar(
            select(EventField.event_id)
            .where(
                EventField.evidence_version_id == chunk.version_id,
                EventField.evidence_page == chunk.page_number,
            )
            .join(Event, Event.id == EventField.event_id)
            .where(Event.event_type_id == event_type.id)
            .limit(1)
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
            supersedes_event_id=superseded_event_id,
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
