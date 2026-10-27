"""Rule- and pattern-based structured extraction (offline, no network).
One real worked extractor (AUD_RESIGN) end-to-end: finds an audit-firm
name and a resignation date in chunk text, verifies each against its own
span (ledgerlight.knowledge.evidence), and persists Event/EventField rows
-- a field that fails verification is still stored (validation_status=
'failed'), never silently dropped, and queues a review_queue item instead
of being promoted. An optional LLM extractor is defined in
ledgerlight.knowledge.llm_extraction, gated on LLM_PROVIDER + an API key
being present -- see that module for the "not run" behaviour when absent.

Only AUD_RESIGN has a real extractor in Phase 2; the other 8 schemas
(ledgerlight.knowledge.extraction_schemas) exist and are tested, but
extracting their fields from this specific small real corpus (shareholding
-pattern tables, rating-rationale PDFs, etc.) needs table/layout extraction
beyond this phase's scope -- documented honestly in the Phase 2 report
rather than stubbed with invented logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ledgerlight.knowledge.evidence import (
    ValidationStatus,
    find_dates_in_text,
    verify_date,
    verify_name,
)

EXTRACTOR_NAME = "aud-resign-rule-v1"
# v2: the field-matching logic below is unchanged; bumped because
# ledgerlight.knowledge.extraction_pipeline's event-creation gate (which
# keys idempotency off this version) now requires `audit_firm` to be
# present before materializing an event -- see that module's docstring
# for the real false positive this fixes.
EXTRACTOR_VERSION = "2"

_KNOWN_AUDIT_FIRMS = [
    "Price Waterhouse & Co Chartered Accountants LLP",
    "Price Waterhouse Chartered Accountants",
    "Deloitte Haskins & Sells",
    "Deloitte Haskins and Sells",
    "KPMG",
    "Ernst & Young",
    "EY",
    "BSR & Co",
    "SRBC & Co",
    "Walker Chandiok & Co",
    "Grant Thornton",
    "BDO",
    "Lodha & Co",
    "Haribhakti & Co",
]


@dataclass
class ExtractedField:
    field_name: str
    value_json: object
    normalized_value: str | None
    char_start: int
    char_end: int
    validation_status: ValidationStatus


def extract_aud_resign_fields(chunk_text: str, chunk_char_start: int) -> list[ExtractedField]:
    """chunk_char_start is the chunk's own char_start within the page's
    raw_text -- every returned span is in PAGE coordinates (chunk_char_start
    + local offset), per the evidence contract (version_id, page, char_start,
    char_end must all refer to the same page's raw_text)."""
    fields: list[ExtractedField] = []

    firm_match: re.Match[str] | None = None
    matched_firm_name = None
    for firm_name in _KNOWN_AUDIT_FIRMS:
        pattern = re.escape(firm_name).replace(r"\ ", r"\s+")
        m = re.search(pattern, chunk_text, re.IGNORECASE)
        if m:
            firm_match = m
            matched_firm_name = firm_name
            break

    if firm_match is not None and matched_firm_name is not None:
        span_text = chunk_text[max(0, firm_match.start() - 20) : firm_match.end() + 20]
        status = verify_name(matched_firm_name, span_text)
        fields.append(
            ExtractedField(
                field_name="audit_firm",
                value_json=matched_firm_name,
                normalized_value=matched_firm_name,
                char_start=chunk_char_start + firm_match.start(),
                char_end=chunk_char_start + firm_match.end(),
                validation_status=status,
            )
        )

    date_match = re.search(r"\b[A-Za-z]+ \d{1,2},? \d{4}\b|\b\d{1,2}-[A-Za-z]+-\d{4}\b", chunk_text)
    if date_match is not None:
        dates = find_dates_in_text(date_match.group(0))
        if dates:
            resignation_date = dates[0]
            status = verify_date(resignation_date, date_match.group(0))
            fields.append(
                ExtractedField(
                    field_name="resignation_date",
                    value_json=resignation_date.isoformat(),
                    normalized_value=resignation_date.isoformat(),
                    char_start=chunk_char_start + date_match.start(),
                    char_end=chunk_char_start + date_match.end(),
                    validation_status=status,
                )
            )

    return fields
