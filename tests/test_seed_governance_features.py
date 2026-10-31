"""Tests for ledgerlight.modelling.seed_governance_features -- pure
logic (no DB), using real event codes from taxonomy-v1.0.yaml."""

from __future__ import annotations

import datetime as dt

from ledgerlight.modelling.seed_governance_features import (
    GovernanceEventRecord,
    compute_governance_features,
)


def _event(known_at: dt.date, code: str, status: str = "candidate") -> GovernanceEventRecord:
    return GovernanceEventRecord(
        code=code,
        known_at=dt.datetime(known_at.year, known_at.month, known_at.day, tzinfo=dt.UTC),
        status=status,
    )


def test_zero_events_gives_all_zero_counts_not_none() -> None:
    values = compute_governance_features([], dt.date(2020, 1, 1))
    assert values["aud_resign_candidate_count_12m"] == 0
    assert values["governance_candidate_total_12m"] == 0
    assert all(v == 0 for v in values.values())


def test_candidate_and_verified_counted_separately() -> None:
    events = [
        _event(dt.date(2019, 6, 1), "AUD_RESIGN", status="candidate"),
        _event(dt.date(2019, 7, 1), "AUD_RESIGN", status="verified"),
    ]
    values = compute_governance_features(events, dt.date(2019, 12, 31))
    assert values["aud_resign_candidate_count_12m"] == 1
    assert values["aud_resign_verified_count_12m"] == 1
    assert values["governance_candidate_total_12m"] == 1
    assert values["governance_verified_total_12m"] == 1


def test_event_outside_12m_window_excluded() -> None:
    events = [_event(dt.date(2018, 1, 1), "AUD_RESIGN")]
    values = compute_governance_features(events, dt.date(2019, 12, 31))
    assert values["aud_resign_candidate_count_12m"] == 0


def test_event_known_after_as_of_excluded_leakage_check() -> None:
    events = [_event(dt.date(2020, 6, 1), "AUD_RESIGN")]
    values = compute_governance_features(events, dt.date(2019, 12, 31))
    assert values["aud_resign_candidate_count_12m"] == 0


def test_rejected_and_needs_review_events_never_loaded() -> None:
    """load_governance_events itself filters these out at the SQL
    level -- this just documents that compute_governance_features has
    no special-casing for them, so the filter MUST happen upstream."""
    events = [_event(dt.date(2019, 6, 1), "AUD_RESIGN", status="rejected")]
    values = compute_governance_features(events, dt.date(2019, 12, 31))
    # compute_governance_features only recognizes 'candidate'/'verified' --
    # a 'rejected' status event is silently uncounted by design.
    assert values["aud_resign_candidate_count_12m"] == 0
    assert values["aud_resign_verified_count_12m"] == 0
