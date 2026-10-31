"""Tests for ledgerlight.modelling.rating_features. The regex itself is
checked separately against real CARE document text (see
docs/phase-3/evidence/rating-pattern-real-sample-check.log); these
cover the pure logic -- ordinal comparison, downgrade counting, the
"never rated" vs "rated and stable" distinction."""

from __future__ import annotations

import datetime as dt
import uuid

from ledgerlight.modelling.rating_features import (
    _RATING_SYMBOL_PATTERN,
    RATING_ORDINAL,
    RatingObservation,
    compute_rating_features,
)


def _obs(known_at: dt.date, symbol: str, negative: bool = False) -> RatingObservation:
    return RatingObservation(
        known_at=dt.datetime(known_at.year, known_at.month, known_at.day, tzinfo=dt.UTC),
        rating_symbol=symbol,
        ordinal=RATING_ORDINAL[symbol],
        negative_outlook=negative,
        version_id=uuid.uuid4(),
        page_number=1,
        char_start=0,
        char_end=len(symbol),
    )


def test_pattern_extracts_real_care_press_release_phrasing() -> None:
    text = "the bonds were rated CARE AA+ and later CARE A- and CARE BBB and CARE D"
    matches = [m.group(1) for m in _RATING_SYMBOL_PATTERN.finditer(text)]
    assert matches == ["AA+", "A-", "BBB", "D"]


def test_pattern_does_not_match_short_term_scale_or_company_name() -> None:
    text = "CARE Analysis Limited rated the commercial paper CARE A1+ as strong"
    matches = [m.group(1) for m in _RATING_SYMBOL_PATTERN.finditer(text)]
    assert matches == []


def test_no_observations_returns_none_not_zero() -> None:
    """Never-rated must be distinguishable from rated-and-stable."""
    result = compute_rating_features([], dt.date(2020, 1, 1))
    assert result.current_rating_ordinal is None
    assert result.rating_actions_count_12m is None
    assert result.downgrades_count_12m is None
    assert result.days_since_last_downgrade is None


def test_single_downgrade_counted_and_dated() -> None:
    observations = [
        _obs(dt.date(2019, 1, 1), "AA"),
        _obs(dt.date(2019, 6, 1), "BBB"),  # real downgrade: AA -> BBB
    ]
    result = compute_rating_features(observations, dt.date(2019, 12, 31))
    assert result.downgrades_count_12m == 1
    assert result.current_rating_ordinal == RATING_ORDINAL["BBB"]
    assert result.days_since_last_downgrade == (dt.date(2019, 12, 31) - dt.date(2019, 6, 1)).days


def test_upgrade_is_not_counted_as_downgrade() -> None:
    observations = [
        _obs(dt.date(2019, 1, 1), "BBB"),
        _obs(dt.date(2019, 6, 1), "AA"),  # real upgrade
    ]
    result = compute_rating_features(observations, dt.date(2019, 12, 31))
    assert result.downgrades_count_12m == 0
    assert result.days_since_last_downgrade is None


def test_future_observations_excluded_from_as_of() -> None:
    """Leakage check: an observation known AFTER as_of must never affect
    the computed features."""
    observations = [
        _obs(dt.date(2019, 1, 1), "AA"),
        _obs(dt.date(2020, 6, 1), "D"),  # known only after as_of below
    ]
    result = compute_rating_features(observations, dt.date(2019, 12, 31))
    assert result.current_rating_ordinal == RATING_ORDINAL["AA"]
    assert result.downgrades_count_12m == 0


def test_negative_outlook_flag_reflects_latest_observation() -> None:
    observations = [
        _obs(dt.date(2019, 1, 1), "AA", negative=False),
        _obs(dt.date(2019, 6, 1), "AA-", negative=True),
    ]
    result = compute_rating_features(observations, dt.date(2019, 12, 31))
    assert result.negative_outlook_flag == 1
