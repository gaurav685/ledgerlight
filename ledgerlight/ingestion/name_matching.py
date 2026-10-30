"""Shared company-name matching for per-company discovery jobs (CARE, IBBI):
deciding whether a search result actually names the SEED-track company a
job queried for, rather than an unrelated subsidiary/group entity that
happens to share a word.

Real motivating cases (see ledgerlight.ingestion.care and .ibbi, and each
module's tests): CARE's search for "Vakrangee" also returns "Vakrangee
Packaging LLP"; IBBI's title search for "Jet Airways" also returns "Metro
Jet Airways Training Pvt. Ltd." -- both unrelated entities that must be
excluded, while real variants of the actual company ("Jet Airways (India)
Ltd." vs "...Limited" vs a data-entry "...Private Limited") must still
match.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypeVar

from rapidfuzz import fuzz

# Applied AFTER stripping common corporate suffixes (see normalize_company_name)
# -- without stripping, a legitimate match like "Vakrangee" vs "Vakrangee
# Limited" scores only ~69 (token_sort_ratio penalizes the extra token),
# while the false positive "Vakrangee" vs "Vakrangee Packaging LLP" scores
# ~56: both low, with too little separation to set a floor on. After
# stripping suffixes the real match hits 100 and the false positive drops
# to ~64. Picked against real data -- see tests/test_care_ingestion.py and
# tests/test_ibbi_ingestion.py.
NAME_MATCH_FLOOR = 75.0

_CORPORATE_SUFFIX_PATTERN = re.compile(
    r"\b(limited|ltd\.?|private|pvt\.?|llp|incorporated|inc\.?|corporation|corp\.?)\b",
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    stripped = _CORPORATE_SUFFIX_PATTERN.sub(" ", name)
    cleaned = re.sub(r"[^a-z0-9 ]", " ", stripped.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def name_match_score(query: str, candidate_name: str) -> float:
    return fuzz.token_sort_ratio(
        normalize_company_name(query), normalize_company_name(candidate_name)
    )


T = TypeVar("T")


def best_name_match(query: str, candidates: list[T], name_of: Callable[[T], str]) -> T | None:
    """Returns the candidate whose name best matches `query` after
    normalization, if its score clears NAME_MATCH_FLOOR -- else None."""
    best: T | None = None
    best_score = 0.0
    for candidate in candidates:
        score = name_match_score(query, name_of(candidate))
        if score > best_score:
            best_score = score
            best = candidate
    if best is not None and best_score >= NAME_MATCH_FLOOR:
        return best
    return None
