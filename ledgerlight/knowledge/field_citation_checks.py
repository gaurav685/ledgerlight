"""Phase 6 Correction 1 Sec4: real citation-integrity checks for
`EventField`, DB-aware (unlike `ledgerlight.knowledge.evidence`'s pure
name/date/number checks). Added after three real field-review findings
passed the existing per-value checks despite being wrong:

- a THERMAX `resignation_date` cited a different person's (a Company
  Secretary's, not the statutory auditor's) own resignation date --
  fixed at the extractor level (see `extraction.py`'s real firm-
  proximity window), not here.
- a RELCAPITAL `order_document` cited a real SEBI order against a
  distinct, related legal entity ("Reliance Capital Asset Management
  Limited"), not the event's own company ("Reliance Capital Limited").
- a BCG `order_document` cited a real but wholly unrelated document --
  "Brightcom" never appears in it at all.

Three checks here, each independent of the others and of the per-value
checks in `evidence.py`:

- `verify_span_within_document`: the cited char range must actually
  fit inside the cited page's own real text.
- `verify_field_type_matches_schema`: the field's value must match the
  type its own event type's schema declares (date/number/str/bool) --
  no schema for this event type is a real, disclosed gap, not a pass.
- `verify_order_document_names_company`: for a document ingested via a
  loose keyword/title search (the real root cause behind both
  wrong-document findings above -- see
  `data/manifests/live_ingestion.jsonl`'s own "matched seed name '...'
  via SEBI's own entity/title/keyword search" coverage notes), the
  search term that found it must actually appear in the document's
  own real text. This catches BCG (the search term never appears at
  all). It does NOT catch RELCAPITAL -- "Reliance Capital" is a real
  substring of the wrong entity's own longer name ("Reliance Capital
  Asset Management Limited"), a genuine name-collision no literal
  containment check can resolve; that one stays a disclosed limitation,
  already flagged PENDING_HUMAN_REVIEW via the Sec1 quarantine (see
  docs/phase-6/review-pack/field-review-audit.jsonl, item
  11278fe7-1ae9-4f96-97db-82d4d3e11dce).

  Deliberately scoped by its caller (scripts/reverify_event_fields.py)
  to SEBI_ORDER_AGAINST_COMPANY's own `order_document` field only --
  trying it against IBBI_CIRP_ADMISSION's `admission_language` real
  corpus produced confirmed false positives from real legal-name
  punctuation variants this check cannot resolve ("Krebs
  Bio-Chemicals & Industries Limited" vs a seed name of "Krebs
  Biochemicals and Industries Limited"; "Diamond Power & Infrastructure
  Ltd." vs "Diamond Power Infrastructure Limited") -- a real,
  disclosed limitation, not silently suppressed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledgerlight.db.models import DocumentPage
from ledgerlight.knowledge.extraction_schemas import EVENT_TYPE_SCHEMAS

FieldCheckStatus = Literal["validated", "failed", "unverifiable"]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LIVE_INGESTION_MANIFEST = REPO_ROOT / "data" / "manifests" / "live_ingestion.jsonl"

_SEED_NAME_PATTERN = re.compile(r"matched seed name '([^']+)' via")


def _latest_page_text(session: Session, version_id: uuid.UUID, page_number: int) -> str | None:
    page = session.scalar(
        select(DocumentPage)
        .where(DocumentPage.version_id == version_id, DocumentPage.page_number == page_number)
        .order_by(DocumentPage.extractor_version.desc())
    )
    return page.raw_text if page is not None else None


def verify_span_within_document(
    session: Session, version_id: uuid.UUID, page_number: int, char_start: int, char_end: int
) -> FieldCheckStatus:
    """The cited (page, char_start, char_end) must really exist inside
    that page's own real, persisted text -- never trusted on the
    strength of the citation's own say-so. A zero-width span
    (char_start == char_end, real for every SEBI_ORDER_AGAINST_COMPANY
    `order_document` field -- see scripts/populate_outcomes.py's own
    "every auto-linked SEBI document is itself the evidence, no
    further text classification") is a deliberate "whole document is
    the evidence" marker, not a defect -- "unverifiable", not
    "failed"."""
    if char_start == char_end:
        return "unverifiable"
    raw_text = _latest_page_text(session, version_id, page_number)
    if raw_text is None:
        return "failed"
    if 0 <= char_start < char_end <= len(raw_text):
        return "validated"
    return "failed"


def verify_field_type_matches_schema(
    event_type_code: str, field_name: str, value_json: object
) -> FieldCheckStatus:
    """A real, disclosed gap: only the 9 governance red-flag event
    types (`ledgerlight.knowledge.extraction_schemas.EVENT_TYPE_SCHEMAS`)
    have a declared field schema -- the 3 outcome-taxonomy event types
    (SEBI_ORDER_AGAINST_COMPANY, IBBI_CIRP_ADMISSION,
    RATING_DOWNGRADE_D) do not, so this returns "unverifiable" for
    those rather than silently passing them as "validated"."""
    schema = EVENT_TYPE_SCHEMAS.get(event_type_code)
    if schema is None:
        return "unverifiable"
    declared = schema.model_fields.get(field_name)
    if declared is None:
        return "failed"
    expected_type = declared.annotation
    # Every schema field is `X | None` -- unwrap to the real X.
    args = getattr(expected_type, "__args__", [expected_type])
    real_types = [t for t in args if t is not type(None)]
    real_type = real_types[0] if real_types else expected_type

    if value_json is None:
        return "unverifiable"
    if real_type is dt.date:
        if isinstance(value_json, str):
            try:
                dt.date.fromisoformat(value_json)
                return "validated"
            except ValueError:
                return "failed"
        return "failed"
    if real_type is Decimal:
        return "validated" if isinstance(value_json, int | float | str) else "failed"
    if real_type is bool:
        return "validated" if isinstance(value_json, bool) else "failed"
    if real_type is str:
        return "validated" if isinstance(value_json, str) else "failed"
    return "unverifiable"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def seed_name_for_retrieval_url(retrieval_url: str) -> str | None:
    """The real search term (company name) that found this document,
    as recorded by the real live-ingestion acquisition job's own
    `coverage_note` -- the one place this project records WHY a
    keyword/title-search-based document was linked to a company. Not
    every document has one (manual/seed entries, or documents linked
    via an exact identifier, never searched by keyword at all)."""
    if not LIVE_INGESTION_MANIFEST.exists():
        return None
    with LIVE_INGESTION_MANIFEST.open(encoding="utf-8") as fh:
        for line in fh:
            if retrieval_url not in line:
                continue
            record = json.loads(line)
            if record.get("retrieval_url") != retrieval_url:
                continue
            match = _SEED_NAME_PATTERN.search(record.get("coverage_note") or "")
            if match:
                return match.group(1)
    return None


def verify_order_document_names_company(
    session: Session, version_id: uuid.UUID, seed_name: str
) -> FieldCheckStatus:
    """The real search term that found this document must appear in
    its own full real text (every page, not just the cited span --
    `order_document`'s whole evidence IS the document). A document
    whose own title matched a company's name via SEBI's keyword
    search, but whose own body never mentions that name at all, is
    the real BCG finding this closes.

    Tried two ways: once with normal whitespace, once with ALL
    whitespace stripped from both sides -- a real, disclosed PDF-
    extraction artifact (confirmed against real NCLT order text, e.g.
    "INTHEMATTEROFM/S.BGRENERGYSYSTEMSLIMITED" with no spaces at all
    between words) would otherwise make this fail on real, correct
    citations, not just the wrong ones."""
    pages = session.scalars(select(DocumentPage).where(DocumentPage.version_id == version_id)).all()
    if not pages:
        return "unverifiable"
    full_text = _normalize("\n".join(p.raw_text for p in pages))
    if _normalize(seed_name) in full_text:
        return "validated"
    stripped_text = re.sub(r"\s+", "", full_text)
    stripped_seed_name = re.sub(r"\s+", "", _normalize(seed_name))
    return "validated" if stripped_seed_name in stripped_text else "failed"
