"""Phase 6 Correction 1 §4.3: re-run the three new citation-integrity
checks (`ledgerlight.knowledge.field_citation_checks`) over every real,
already-stored `EventField` row, independent of the per-value checks
that already ran at extraction time.

Never mutates `EventField.validation_status` -- that column records
what the ORIGINAL per-value check found, and stays exactly as it was.
A field that newly fails one of these three checks gets a NEW
`ReviewQueueItem` instead (idempotent: re-running this script never
creates a duplicate for the same field+rule), so "nothing is
overwritten" the same way every other correction in this phase works.

Usage:
    python3 -m uv run python scripts/reverify_event_fields.py [--apply]

Without --apply, prints what WOULD be queued (a dry run). --apply
commits the new review_queue rows.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document, DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.field_citation_checks import (  # noqa: E402
    FieldCheckStatus,
    seed_name_for_retrieval_url,
    verify_field_type_matches_schema,
    verify_order_document_names_company,
    verify_span_within_document,
)
from ledgerlight.knowledge.models import Event, EventField, EventType, ReviewQueueItem  # noqa: E402

REASON_PREFIX = "correction1_sec4_"


def _already_queued(session: Session, field_id: uuid.UUID, reason_code: str) -> bool:
    return (
        session.scalar(
            select(ReviewQueueItem.id).where(
                ReviewQueueItem.item_type == "event_field",
                ReviewQueueItem.reference_id == field_id,
                ReviewQueueItem.reason_code == reason_code,
            )
        )
        is not None
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-verify every real EventField.")
    parser.add_argument("--apply", action="store_true", help="commit new review_queue rows")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    counts: dict[str, int] = {}
    # (event_type, field_name, rule, field_id)
    new_review_items: list[tuple[str, str, str, str]] = []
    version_source_key: dict[uuid.UUID, str] = {}

    with session_factory() as session:
        fields = session.scalars(select(EventField).order_by(EventField.id)).all()
        print(f"total event_fields: {len(fields)}")

        for field in fields:
            event = session.get(Event, field.event_id)
            assert event is not None, f"event_field {field.id} has no real event"
            event_type = session.get(EventType, event.event_type_id)
            assert event_type is not None, f"event {event.id} has no real event_type"
            counts[f"{event_type.code}:{field.field_name}:total"] = (
                counts.get(f"{event_type.code}:{field.field_name}:total", 0) + 1
            )

            rule_b: FieldCheckStatus = verify_span_within_document(
                session,
                field.evidence_version_id,
                field.evidence_page,
                field.evidence_char_start,
                field.evidence_char_end,
            )
            rule_c: FieldCheckStatus = verify_field_type_matches_schema(
                event_type.code, field.field_name, field.value_json
            )

            # Sec4's own real finding: this check produces confirmed false
            # positives against IBBI_CIRP_ADMISSION's real corpus (legal-name
            # punctuation variants it cannot resolve -- see
            # field_citation_checks.py's own module docstring). Deliberately
            # scoped to SEBI_ORDER_AGAINST_COMPANY's order_document field,
            # where it was built against and verified.
            rule_a: FieldCheckStatus = "unverifiable"
            is_sebi_order_document = (
                event_type.code == "SEBI_ORDER_AGAINST_COMPANY"
                and field.field_name == "order_document"
            )
            if is_sebi_order_document:
                source_key = version_source_key.get(field.evidence_version_id)
                if source_key is None:
                    version = session.get(DocumentVersion, field.evidence_version_id)
                    document = session.get(Document, version.document_id) if version else None
                    source_key = document.source_key if document else ""
                    version_source_key[field.evidence_version_id] = source_key
                seed_name = seed_name_for_retrieval_url(source_key) if source_key else None
                if seed_name:
                    rule_a = verify_order_document_names_company(
                        session, field.evidence_version_id, seed_name
                    )

            for rule_name, status in (
                ("span_bounds", rule_b),
                ("field_type", rule_c),
                ("order_document_identity", rule_a),
            ):
                counts[f"{rule_name}:{status}"] = counts.get(f"{rule_name}:{status}", 0) + 1
                if status == "failed" and field.validation_status == "validated":
                    reason_code = f"{REASON_PREFIX}{rule_name}"
                    if not _already_queued(session, field.id, reason_code):
                        new_review_items.append(
                            (event_type.code, field.field_name, rule_name, str(field.id))
                        )
                        if args.apply:
                            session.add(
                                ReviewQueueItem(
                                    item_type="event_field",
                                    reference_id=field.id,
                                    reason_code=reason_code,
                                    priority=2,
                                    status="open",
                                )
                            )

        if args.apply and new_review_items:
            session.commit()

    rule_keys = ("span_bounds", "field_type", "order_document_identity")
    print("\n--- per-rule status counts ---")
    for key, count in sorted(counts.items()):
        if ":" in key and key.split(":")[0] in rule_keys:
            print(f"  {key}: {count}")

    action = "created" if args.apply else "WOULD be created (dry run, pass --apply to commit)"
    print(f"\n--- {len(new_review_items)} new review_queue item(s) {action} ---")
    for event_type_code, field_name, rule_name, field_id in new_review_items:
        print(f"  {event_type_code}:{field_name} failed {rule_name} -- event_field {field_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
