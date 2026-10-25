from __future__ import annotations

import datetime as dt

from ledgerlight.common.timeutil import ist_date_to_utc
from ledgerlight.db.temporal import compute_known_at

RETRIEVED = dt.datetime(2026, 1, 10, tzinfo=dt.UTC)
PUBLISHED = dt.datetime(2019, 6, 5, tzinfo=dt.UTC)
SNAPSHOT = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)


def test_reliable_source_uses_published_at() -> None:
    known_at, basis = compute_known_at(
        source_id="sebi", published_at=PUBLISHED, snapshot_at=None, retrieved_at=RETRIEVED
    )
    assert known_at == PUBLISHED
    assert basis == "published_at"


def test_unreliable_source_ignores_published_at_falls_back_to_retrieved() -> None:
    known_at, basis = compute_known_at(
        source_id="jetairways_ir", published_at=PUBLISHED, snapshot_at=None, retrieved_at=RETRIEVED
    )
    assert known_at == RETRIEVED
    assert basis == "retrieved_at"


def test_unreliable_source_with_snapshot_uses_snapshot() -> None:
    known_at, basis = compute_known_at(
        source_id="jetairways_ir",
        published_at=PUBLISHED,
        snapshot_at=SNAPSHOT,
        retrieved_at=RETRIEVED,
    )
    assert known_at == SNAPSHOT
    assert basis == "snapshot_at"


def test_reliable_source_without_published_at_falls_back_to_retrieved() -> None:
    known_at, basis = compute_known_at(
        source_id="ibbi", published_at=None, snapshot_at=None, retrieved_at=RETRIEVED
    )
    assert known_at == RETRIEVED
    assert basis == "retrieved_at"


def test_reliable_source_without_published_at_uses_snapshot_before_retrieved() -> None:
    known_at, basis = compute_known_at(
        source_id="care", published_at=None, snapshot_at=SNAPSHOT, retrieved_at=RETRIEVED
    )
    assert known_at == SNAPSHOT
    assert basis == "snapshot_at"


def test_never_earlier_than_evidence_all_none_except_retrieved() -> None:
    known_at, basis = compute_known_at(
        source_id="some_new_source", published_at=None, snapshot_at=None, retrieved_at=RETRIEVED
    )
    assert known_at == RETRIEVED
    assert basis == "retrieved_at"


def test_ist_date_to_utc_is_ist_midnight_in_utc() -> None:
    result = ist_date_to_utc(dt.date(2019, 6, 5))
    # IST is UTC+5:30, so IST midnight on the 5th is 18:30 UTC on the 4th.
    assert result == dt.datetime(2019, 6, 4, 18, 30, tzinfo=dt.UTC)
