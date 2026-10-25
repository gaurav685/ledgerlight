"""The known_at rule — see docs/data/temporal-semantics.md for the full
rationale. Implemented as one small, pure, tested function so every
ingestion path computes it the same way.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

KnownAtBasis = Literal["published_at", "snapshot_at", "retrieved_at"]

# Sources whose stated publication timestamp is trustworthy evidence of
# when a document became publicly known. Company IR sources are
# deliberately excluded: a shareholding pattern's stated date is the
# reporting *period end* ("as of 31 Mar"), not when it was actually
# published — using it as known_at would claim knowledge earlier than the
# evidence supports, which the rule explicitly forbids.
RELIABLE_PUBLISHED_AT_SOURCES: frozenset[str] = frozenset({"sebi", "ibbi", "care", "nse_archives"})


def compute_known_at(
    *,
    source_id: str,
    published_at: dt.datetime | None,
    snapshot_at: dt.datetime | None,
    retrieved_at: dt.datetime,
) -> tuple[dt.datetime, KnownAtBasis]:
    """known_at = earliest TRUSTWORTHY evidence of public availability.

    1. source's stated publication timestamp, if that source is on the
       reliable list
    2. else the archive snapshot_at
    3. else retrieved_at

    Never returns a basis whose timestamp is later than an available
    earlier basis would allow, and never uses published_at from a source
    not marked reliable (that would risk inferring an earlier known_at
    than the evidence actually supports).
    """
    if published_at is not None and source_id in RELIABLE_PUBLISHED_AT_SOURCES:
        return published_at, "published_at"
    if snapshot_at is not None:
        return snapshot_at, "snapshot_at"
    return retrieved_at, "retrieved_at"
