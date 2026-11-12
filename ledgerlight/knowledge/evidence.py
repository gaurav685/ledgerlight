"""Evidence verification: every extracted field value is checked against
its cited span before being trusted. A value that fails is stored with
validation_status='failed' and is never promoted -- see
ledgerlight.knowledge.extraction and docs/knowledge/extraction.md.

Three verification rules, one per value shape:
- names/free text: normalized substring containment (case-insensitive,
  whitespace-collapsed) -- the value must appear in the span, verbatim
  modulo whitespace/case.
- dates: parsed-date equality (the span's date, however formatted, must
  parse to the same calendar date as the claimed value).
- numbers/percentages: numeric equality within an explicit tolerance
  (handles OCR/typesetting noise like "55.0" vs "55" or a stray space).

Plus one shared negation primitive (Phase 6 Correction 1 §5), used by
both the real AUD_RESIGN detector (ledgerlight.knowledge.extraction)
and the silver label proposer (ledgerlight.knowledge.labeling) -- real
corpus text cites a negated resignation ("there has been no
resignation of the statutory auditors during the year") as if it were
positive evidence without this.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Literal

ValidationStatus = Literal["validated", "failed", "unverifiable"]

NUMERIC_TOLERANCE = Decimal("0.01")

# A negating word ("no", "not", "nil", "never", "none") immediately
# before a trigger match -- "no resignation", "has not resigned",
# "none of the Independent Directors ... have resigned" are all real
# dev/validation corpus examples (see
# docs/phase-6/evidence/sec5-negation-hardening.md).
NEGATION_PATTERN = re.compile(r"\b(?:no|not|nil|never|none)\b", re.IGNORECASE)
NEGATION_WINDOW_CHARS = 80


def is_negated_before(text: str, position: int, window: int = NEGATION_WINDOW_CHARS) -> bool:
    """A negating word appears in the `window` characters immediately
    before `position`, truncated at the nearest preceding sentence
    boundary (".") so an unrelated EARLIER sentence's own negation
    can't bleed into a later, real positive. Deliberately a short,
    disclosed heuristic, not a dependency parse: real corpus negations
    found so far all fit within one un-punctuated clause, which this
    covers; a real negation separated from its verb by a full sentence
    break would not be caught -- a disclosed, real limitation, not
    attempted here."""
    start = max(0, position - window)
    preceding = text[start:position]
    last_period = preceding.rfind(".")
    if last_period != -1:
        preceding = preceding[last_period + 1 :]
    return bool(NEGATION_PATTERN.search(preceding))


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_name(value: str, span_text: str) -> ValidationStatus:
    """Normalized substring containment: case-insensitive,
    whitespace-collapsed. Handles a span like "...PRICE WATERHOUSE & CO\\n
    CHARTERED ACCOUNTANTS LLP..." matching value "Price Waterhouse & Co
    Chartered Accountants LLP" (real corpus example)."""
    if not value or not span_text:
        return "unverifiable"
    return "validated" if _normalize_text(value) in _normalize_text(span_text) else "failed"


_DATE_PATTERNS = [
    "%d-%b-%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %Y",  # commas are stripped before matching, see below
    "%b %d %Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
]


def find_dates_in_text(text: str) -> list[dt.date]:
    found: list[dt.date] = []
    # A handful of common real-filing date shapes, tried against every
    # plausible substring window -- not a full NLP date-extractor, just
    # enough to verify a CLAIMED date appears somewhere in the span.
    date_pattern = (
        r"\b\d{1,2}[-/ ](?:[A-Za-z]+|\d{1,2})[-/ ]\d{4}\b"
        r"|\b[A-Za-z]+ \d{1,2},? \d{4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b"
    )
    candidates = re.findall(date_pattern, text)
    for candidate in candidates:
        normalized_candidate = candidate.replace(",", "")
        for fmt in _DATE_PATTERNS:
            try:
                found.append(dt.datetime.strptime(normalized_candidate, fmt).date())
                break
            except ValueError:
                continue
    return found


def verify_date(value: dt.date, span_text: str) -> ValidationStatus:
    if span_text is None:
        return "unverifiable"
    dates_in_span = find_dates_in_text(span_text)
    if not dates_in_span:
        return "unverifiable"
    return "validated" if value in dates_in_span else "failed"


def verify_number(
    value: Decimal, span_text: str, *, tolerance: Decimal = NUMERIC_TOLERANCE
) -> ValidationStatus:
    if not span_text:
        return "unverifiable"
    numbers_in_span = [
        Decimal(m.replace(",", "")) for m in re.findall(r"\d[\d,]*\.?\d*", span_text) if m
    ]
    if not numbers_in_span:
        return "unverifiable"
    for candidate in numbers_in_span:
        if abs(candidate - value) <= tolerance:
            return "validated"
    return "failed"
