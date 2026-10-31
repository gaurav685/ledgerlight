"""RULE-VERIFIED (rule-extracted, span-verified) rating and auto-link
features for Phase 3 Sec4.2's UNIVERSE track -- per the brief: "ratings:
counts of actions, downgrades and negative watches/outlooks, the
current rating bucket, time since the last downgrade" and "prior SEBI
orders and prior IBBI-related mentions, via auto-links."

Rating symbols are extracted with a literal, case-sensitive regex over
real CARE `DocumentPage` text -- the same style of rule as
`scripts/populate_outcomes.py`'s `_RATING_D_PATTERN`, generalized to
CARE's full long-term grade scale (AAA down to D). Tested against 40
real CARE document pages before use (see
docs/phase-3/evidence/rating-pattern-real-sample-check.log) -- NOT the
Phase 2 zero-shot RATING_ACT detector, which is EVENT-CANDIDATE tier,
not RULE-VERIFIED, per the brief's own feature policy.

A CARE document can state ratings for several instruments of the same
issuer at different grades (e.g. one bond at D, another at B+). This
module conservatively takes the WORST (lowest-ordinal) grade mentioned
on a document's first page as that document's own rating observation --
a disclosed simplification, not a claim of a single official
"corporate rating"."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session

# Best to worst -- index is the ordinal (0 = best, higher = worse).
RATING_SCALE: list[str] = [
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
    "B-",
    "C+",
    "C",
    "C-",
    "D",
]
RATING_ORDINAL: dict[str, int] = {symbol: idx for idx, symbol in enumerate(RATING_SCALE)}

_RATING_SYMBOL_PATTERN = re.compile(
    r"CARE\s+(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|C[+-]?|D)(?![A-Za-z0-9])"
)
_NEGATIVE_OUTLOOK_PATTERN = re.compile(r"negative\s+(outlook|watch)", re.I)


@dataclass
class RatingObservation:
    known_at: dt.datetime
    rating_symbol: str
    ordinal: int
    negative_outlook: bool
    version_id: uuid.UUID
    page_number: int
    char_start: int
    char_end: int


def extract_rating_observations(session: Session, company_id: uuid.UUID) -> list[RatingObservation]:
    """Real rating observations for one company, oldest first. Only
    CARE documents already auto-linked to this company via `Filing`
    (Sec2.3/2.4) are considered -- never a bare text search unscoped to
    a real, auto-linked company."""
    rows = session.execute(
        text(
            """
            SELECT dv.known_at, dp.page_number, dp.raw_text, dp.id, dv.id
            FROM filings f
            JOIN documents d ON d.id = (
                SELECT document_id FROM document_versions WHERE id = f.version_id
            )
            JOIN document_versions dv ON dv.id = f.version_id
            JOIN document_pages dp ON dp.version_id = dv.id
            WHERE f.company_id = :company_id AND d.source_id = 'care' AND dp.page_number = 1
            ORDER BY dv.known_at
            """
        ),
        {"company_id": company_id},
    ).all()

    observations: list[RatingObservation] = []
    for row in rows:
        known_at = cast(dt.datetime, row[0])
        page_number = cast(int, row[1])
        raw_text = cast(str, row[2])
        version_id = cast(uuid.UUID, row[4])
        matches = list(_RATING_SYMBOL_PATTERN.finditer(raw_text))
        if not matches:
            continue
        worst = max(matches, key=lambda m: RATING_ORDINAL[m.group(1)])
        window = raw_text[max(0, worst.start() - 100) : worst.end() + 100]
        observations.append(
            RatingObservation(
                known_at=known_at,
                rating_symbol=worst.group(1),
                ordinal=RATING_ORDINAL[worst.group(1)],
                negative_outlook=bool(_NEGATIVE_OUTLOOK_PATTERN.search(window)),
                version_id=version_id,
                page_number=page_number,
                char_start=worst.start(1),
                char_end=worst.end(1),
            )
        )
    observations.sort(key=lambda o: o.known_at)
    return observations


@dataclass
class RatingFeatureValues:
    rating_actions_count_12m: int | None
    downgrades_count_12m: int | None
    current_rating_ordinal: int | None
    days_since_last_downgrade: int | None
    negative_outlook_flag: int | None


def compute_rating_features(
    observations: list[RatingObservation], as_of: dt.date
) -> RatingFeatureValues:
    """All real -- never fabricated. `None` (not 0) when no rating has
    ever been observed for this company as of `as_of`, so a model can't
    confuse "never rated" with "rated and stable"."""
    known = [o for o in observations if o.known_at.date() <= as_of]
    if not known:
        return RatingFeatureValues(None, None, None, None, None)

    window_start = as_of - dt.timedelta(days=365)
    in_window = [o for o in known if o.known_at.date() > window_start]

    downgrades_12m = 0
    for i in range(1, len(in_window)):
        if in_window[i].ordinal > in_window[i - 1].ordinal:
            downgrades_12m += 1

    last_downgrade_date: dt.date | None = None
    for i in range(1, len(known)):
        if known[i].ordinal > known[i - 1].ordinal:
            last_downgrade_date = known[i].known_at.date()

    days_since_last_downgrade = (
        (as_of - last_downgrade_date).days if last_downgrade_date is not None else None
    )

    return RatingFeatureValues(
        rating_actions_count_12m=len(in_window),
        downgrades_count_12m=downgrades_12m,
        current_rating_ordinal=known[-1].ordinal,
        days_since_last_downgrade=days_since_last_downgrade,
        negative_outlook_flag=int(known[-1].negative_outlook),
    )


def count_prior_filings(
    session: Session, company_id: uuid.UUID, source_id: str, as_of: dt.date
) -> int:
    """Real count of Filing rows for this company, this source, with
    known_at <= as_of -- the auto-link-based "prior SEBI orders" /
    "prior IBBI-related mentions" features."""
    result = session.execute(
        text(
            """
            SELECT count(*) FROM filings f
            JOIN document_versions dv ON dv.id = f.version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE f.company_id = :company_id AND d.source_id = :source_id
              AND dv.known_at <= :as_of
            """
        ),
        {"company_id": company_id, "source_id": source_id, "as_of": as_of},
    ).scalar()
    return int(result or 0)
