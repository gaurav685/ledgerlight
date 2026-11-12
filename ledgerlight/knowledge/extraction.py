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
    is_negated_before,
    verify_date,
    verify_name,
)

EXTRACTOR_NAME = "aud-resign-rule-v1"
# v4 (Phase 6 Correction 1 Sec5): the firm-anchored date window (v3,
# Sec4) still extracted ANY date near a known firm name, with no
# requirement that the firm mention be about a resignation AT ALL --
# a real, bigger-than-expected finding: scanning the whole real
# corpus found 40+ real chunks where a firm name merely co-occurred
# with an unrelated date (a signature block, a financial-statement
# note, a court-hearing date) and no "resign"/"cease" word anywhere
# in the chunk, yet still produced a resignation_date. v4 requires a
# real, non-negated "resign"/"cease" word inside the same firm-
# anchored window before a date is extracted at all -- this also
# covers the narrower negation case ("KPMG continues as our statutory
# auditor; there has been no resignation this year" with some
# unrelated nearby date). See
# docs/phase-6/evidence/sec5-negation-hardening.md for the full real
# before/after. Bumped because
# ledgerlight.knowledge.extraction_pipeline's event-creation gate keys
# idempotency off this version.
EXTRACTOR_VERSION = "4"

_RESIGN_OR_CEASE_PATTERN = re.compile(r"resign|ceas(?:e|ed|ing)", re.IGNORECASE)

DATE_SEARCH_WINDOW_CHARS = 300
"""How far around the real firm mention to look for its resignation
date -- wide enough for "KPMG ... has resigned ... effective April 28,
2018" (the real corpus phrasing), narrow enough to exclude an
unrelated date elsewhere in the same chunk (the real THERMAX finding:
a Company Secretary's own resignation date, far from the auditor
mention).

Real, disclosed limitation found while validating Sec5 (not
introduced by it -- already true of v3): a real Vakrangee covering
letter has its date in the letterhead (the very top of the page) and
its firm/resign language later in the body, more than this many chars
apart -- neither v3 nor v4 extracts a resignation_date from it today.
Widening this window would risk reopening the original THERMAX bug
this constant exists to prevent; narrowing the gap properly needs a
"nearest real date in the whole chunk, once firm+resign evidence
exists anywhere in it" design (closer to how
ledgerlight.knowledge.labeling._aud_resign already does it), not
attempted here -- flagged for separate, deliberate follow-up."""

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

    # Phase 6 Correction 1 Sec4: a real finding -- the date search used
    # to scan the WHOLE chunk for the first date-shaped string,
    # independent of where (or whether) the audit firm itself was
    # mentioned. A real THERMAX chunk that also named a Company
    # Secretary's own, unrelated resignation date picked up THAT date
    # for this AUD_RESIGN event instead. Only a date near the real
    # firm mention is now considered -- no firm match, no date claim,
    # matching this schema's own "never infer" rule (see this module's
    # docstring): there is no firm context to anchor a resignation
    # date to.
    if firm_match is not None:
        window_start = max(0, firm_match.start() - DATE_SEARCH_WINDOW_CHARS)
        window_end = min(len(chunk_text), firm_match.end() + DATE_SEARCH_WINDOW_CHARS)
        search_text = chunk_text[window_start:window_end]
        # Phase 6 Correction 1 Sec5: a real, non-negated "resign"/
        # "cease" word must exist in this same window -- "KPMG
        # continues as our statutory auditor; there has been no
        # resignation this year" with some unrelated nearby date must
        # not extract that date as a resignation_date.
        has_real_resign_language = any(
            not is_negated_before(search_text, m.start())
            for m in _RESIGN_OR_CEASE_PATTERN.finditer(search_text)
        )
        date_match = (
            re.search(r"\b[A-Za-z]+ \d{1,2},? \d{4}\b|\b\d{1,2}-[A-Za-z]+-\d{4}\b", search_text)
            if has_real_resign_language
            else None
        )
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
                        char_start=chunk_char_start + window_start + date_match.start(),
                        char_end=chunk_char_start + window_start + date_match.end(),
                        validation_status=status,
                    )
                )

    return fields
