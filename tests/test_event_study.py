"""Tests for ledgerlight.research.event_study -- Enhancement 1.

Pure unit tests for the statistical core (market-model fitting,
abnormal returns, CAR, the three significance tests, Holm correction,
the confounding filter, placebo determinism) against hand-computed
synthetic fixtures -- no DB needed. The spec-hash freeze guard is a
real integration test against the live DB (`load_and_verify_spec`,
`model_registry`)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.research.event_study import (
    CONFOUNDING_WINDOW_DAYS,
    MIN_ESTIMATION_DAYS,
    CorradoRankInput,
    EventSarInput,
    abnormal_returns,
    bmp_standardized_test,
    car_for_window,
    corrado_rank_test,
    cross_sectional_t_test,
    downgrade_severity_band,
    find_confounded_keys,
    first_trading_day_at_or_after,
    fit_market_model,
    holm_bonferroni,
    load_and_verify_spec,
    placebo_percentile,
    placebo_seed,
    rating_transition_direction,
    run_placebo,
    simple_returns,
    trading_day_offsets,
)

# --- synthetic trading-day index: skips real weekends AND one real holiday --

_HOLIDAY = dt.date(2024, 1, 26)  # Republic Day -- deliberately absent


def _synthetic_trading_days(start: dt.date, n_business_days: int) -> list[dt.date]:
    days: list[dt.date] = []
    current = start
    while len(days) < n_business_days:
        if current.weekday() < 5 and current != _HOLIDAY:  # Mon-Fri, not the holiday
            days.append(current)
        current += dt.timedelta(days=1)
    return days


TRADING_DAYS = _synthetic_trading_days(dt.date(2024, 1, 1), 400)


# --- simple_returns / trading_day_offsets / first_trading_day_at_or_after ---


def test_simple_returns_hand_computed() -> None:
    d0, d1, d2 = TRADING_DAYS[0], TRADING_DAYS[1], TRADING_DAYS[2]
    closes = {d0: 100.0, d1: 110.0, d2: 99.0}
    returns = simple_returns(closes, TRADING_DAYS[:3])
    assert returns[d1] == pytest.approx(0.10)
    assert returns[d2] == pytest.approx((99.0 - 110.0) / 110.0)
    assert d0 not in returns  # no prior day to compute a return against


def test_trading_day_offsets_skips_the_real_holiday_and_weekends() -> None:
    """2024-01-26 is a Friday in the real Gregorian calendar, but is
    deliberately excluded from this synthetic index (the "real
    holiday" this fixture models) -- offsets must skip straight past
    it, never silently counting it as a real trading day."""
    assert _HOLIDAY.weekday() == 4  # a real Friday
    assert _HOLIDAY not in TRADING_DAYS
    day_before_holiday = dt.date(2024, 1, 25)
    assert day_before_holiday in TRADING_DAYS
    zero_idx = TRADING_DAYS.index(day_before_holiday)
    offsets = trading_day_offsets(TRADING_DAYS, day_before_holiday, range(0, 3))
    # +1 real trading day after 2024-01-25 skips the 26th (holiday) AND
    # the 27th/28th (a real weekend), landing on Monday 2024-01-29.
    assert offsets == TRADING_DAYS[zero_idx : zero_idx + 3]
    assert offsets[1] == dt.date(2024, 1, 29)


def test_trading_day_offsets_omits_out_of_range_offsets() -> None:
    first_day = TRADING_DAYS[0]
    offsets = trading_day_offsets(TRADING_DAYS, first_day, range(-5, 2))
    assert offsets == TRADING_DAYS[0:2]  # the -5..-1 offsets simply don't exist


def test_first_trading_day_at_or_after_maps_a_weekend_announcement_to_monday() -> None:
    # Pick a real Saturday not in TRADING_DAYS, confirm it maps to the
    # next real trading day (Monday), never to the Saturday itself.
    candidates = (TRADING_DAYS[0] + dt.timedelta(days=i) for i in range(14))
    some_saturday = next(d for d in candidates if d.weekday() == 5)
    assert some_saturday not in TRADING_DAYS
    mapped = first_trading_day_at_or_after(TRADING_DAYS, some_saturday)
    assert mapped is not None
    assert mapped in TRADING_DAYS
    assert mapped > some_saturday
    assert mapped.weekday() < 5


# --- market-model fit: hand-computable, noiseless synthetic fixture --------


def _noiseless_fixture(
    n_days: int, alpha: float, beta: float
) -> tuple[dict[dt.date, float], dict[dt.date, float], list[dt.date]]:
    """A deterministic, zero-residual synthetic series: market returns
    oscillate in a fixed, non-random pattern; event returns are built
    EXACTLY as alpha + beta * market_return, so the real OLS fit must
    recover alpha/beta to floating-point precision, and
    `residual_std` must come out at ~0 -- a fully hand-verifiable
    fixture, not a fabricated "it looks about right" check."""
    days = TRADING_DAYS[:n_days]
    market_returns = {d: 0.001 * ((i % 7) - 3) for i, d in enumerate(days)}
    event_returns = {d: alpha + beta * market_returns[d] for d in days}
    return event_returns, market_returns, days


def test_fit_market_model_recovers_known_alpha_beta_on_a_noiseless_fixture() -> None:
    event_returns, market_returns, days = _noiseless_fixture(
        MIN_ESTIMATION_DAYS + 10, alpha=0.0005, beta=1.4
    )
    fit = fit_market_model(event_returns, market_returns, days)
    assert fit is not None
    assert fit.alpha == pytest.approx(0.0005, abs=1e-9)
    assert fit.beta == pytest.approx(1.4, abs=1e-9)
    assert fit.residual_std == pytest.approx(0.0, abs=1e-9)
    assert fit.n_days == MIN_ESTIMATION_DAYS + 10


def test_fit_market_model_returns_none_below_the_real_minimum_estimation_days() -> None:
    event_returns, market_returns, days = _noiseless_fixture(
        MIN_ESTIMATION_DAYS - 1, alpha=0.0, beta=1.0
    )
    assert fit_market_model(event_returns, market_returns, days) is None


def test_abnormal_return_arithmetic_on_a_hand_computed_fixture() -> None:
    """A real, hand-computable abnormal-return check: fit a noiseless
    market model on the estimation window, then inject a KNOWN,
    exact abnormal jump on one specific event-window day and confirm
    the computed AR on that day equals the injected jump to floating
    precision -- and that every OTHER day's AR is exactly 0 (since
    the fixture is noiseless by construction)."""
    alpha, beta = 0.001, 1.2
    event_returns, market_returns, est_days = _noiseless_fixture(MIN_ESTIMATION_DAYS, alpha, beta)
    fit = fit_market_model(event_returns, market_returns, est_days)
    assert fit is not None

    event_day = TRADING_DAYS[MIN_ESTIMATION_DAYS + 5]
    market_returns_full = dict(market_returns)
    market_returns_full[event_day] = 0.004
    injected_abnormal = 0.07
    event_returns_full = dict(event_returns)
    event_returns_full[event_day] = (
        alpha + beta * market_returns_full[event_day] + injected_abnormal
    )

    ar = abnormal_returns(event_returns_full, market_returns_full, fit, [*est_days, event_day])
    assert ar[event_day] == pytest.approx(injected_abnormal, abs=1e-9)
    for d in est_days:
        assert ar[d] == pytest.approx(0.0, abs=1e-9)

    car, n = car_for_window(ar, [event_day])
    assert n == 1
    assert car == pytest.approx(injected_abnormal, abs=1e-9)


def test_car_for_window_reports_real_n_not_requested_window_length() -> None:
    """Spec §7's own per-window-N rule: a day genuinely missing from
    the real AR series must shrink the real N, never be silently
    treated as a zero-AR day."""
    d1, d2, d3 = TRADING_DAYS[0], TRADING_DAYS[1], TRADING_DAYS[2]
    ar_by_day = {d1: 0.01, d3: -0.02}  # d2 has no real data at all
    car, n = car_for_window(ar_by_day, [d1, d2, d3])
    assert n == 2
    assert car == pytest.approx(0.01 - 0.02)


# --- confounding filter (pure) ----------------------------------------------


def test_find_confounded_keys_flags_both_events_within_the_window() -> None:
    company = uuid.uuid4()
    d1 = dt.date(2024, 3, 1)
    d2 = d1 + dt.timedelta(days=CONFOUNDING_WINDOW_DAYS)  # exactly at the boundary
    confounded = find_confounded_keys({company: [d1, d2]}, CONFOUNDING_WINDOW_DAYS)
    assert confounded == {(company, d1), (company, d2)}


def test_find_confounded_keys_does_not_flag_events_just_outside_the_window() -> None:
    company = uuid.uuid4()
    d1 = dt.date(2024, 3, 1)
    d2 = d1 + dt.timedelta(days=CONFOUNDING_WINDOW_DAYS + 1)
    confounded = find_confounded_keys({company: [d1, d2]}, CONFOUNDING_WINDOW_DAYS)
    assert confounded == set()


def test_find_confounded_keys_ignores_a_different_companys_nearby_event() -> None:
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    d1 = dt.date(2024, 3, 1)
    d2 = d1 + dt.timedelta(days=1)
    confounded = find_confounded_keys({company_a: [d1], company_b: [d2]}, CONFOUNDING_WINDOW_DAYS)
    assert confounded == set()


# --- significance tests: structural validation (null vs. strong signal) ---


def _fixture_with_small_deterministic_noise(
    n_days: int, alpha: float, beta: float, phase: int = 0
) -> tuple[dict[dt.date, float], dict[dt.date, float], list[dt.date]]:
    """Like `_noiseless_fixture`, but with a small, fixed, deterministic
    (never random) residual added to each estimation-window day --
    BMP's forecast-error standardization and the Corrado rank test's
    own null-variance estimate both need REAL dispersion in the
    estimation window to produce a well-defined (non-degenerate)
    statistic; a perfectly zero-residual fixture (correct for testing
    the plain OLS/AR arithmetic itself) makes their own variance
    estimate exactly zero, which is a real edge case of those
    formulas, not a bug in them. `phase` shifts the deterministic
    noise pattern per-event, so a cross-sectional group of these
    fixtures has genuine real variation across events, never 20
    identical copies of the same single series."""
    days = TRADING_DAYS[:n_days]
    market_returns = {d: 0.001 * ((i % 7) - 3) for i, d in enumerate(days)}
    event_returns = {
        d: alpha
        + beta * market_returns[d]
        + 0.0004 * ((-1) ** (i + phase)) * (1 + ((i + phase) % 5))
        for i, d in enumerate(days)
    }
    return event_returns, market_returns, days


def _event_inputs_with_known_car(
    n_events: int, car_value: float, n_estimation_days: int = MIN_ESTIMATION_DAYS
) -> tuple[list[EventSarInput], list[CorradoRankInput], list[float]]:
    """`n_events` synthetic, independent events, each with the SAME
    exact real injected CAR value on a 1-day primary window, built on
    a market-model fit with real (small, deterministic) estimation-
    window dispersion -- lets the three significance tests be
    checked against a known, hand-reasoned signal rather than opaque
    real data, without the degenerate zero-variance edge case a fully
    noiseless fixture would hit."""
    sar_inputs: list[EventSarInput] = []
    rank_inputs: list[CorradoRankInput] = []
    cars: list[float] = []
    for i in range(n_events):
        alpha, beta = 0.0, 1.0
        event_returns, market_returns, est_days = _fixture_with_small_deterministic_noise(
            n_estimation_days, alpha, beta, phase=i
        )
        fit = fit_market_model(event_returns, market_returns, est_days)
        assert fit is not None
        event_day = TRADING_DAYS[n_estimation_days + 20 + i]  # distinct day per event
        market_returns_full = dict(market_returns)
        market_returns_full[event_day] = 0.002
        event_returns_full = dict(event_returns)
        event_returns_full[event_day] = alpha + beta * market_returns_full[event_day] + car_value
        ar = abnormal_returns(event_returns_full, market_returns_full, fit, [*est_days, event_day])
        sar_inputs.append(
            EventSarInput(
                fit=fit, ar_by_day=ar, market_returns=market_returns_full, window_days=[event_day]
            )
        )
        rank_inputs.append(
            CorradoRankInput(
                ar_by_day=ar,
                all_pooled_days=[*est_days, event_day],
                estimation_days=est_days,
                window_days=[event_day],
            )
        )
        car, n = car_for_window(ar, [event_day])
        assert n == 1
        cars.append(car)
    return sar_inputs, rank_inputs, cars


def test_cross_sectional_t_test_is_not_significant_under_a_real_null_signal() -> None:
    _, _, cars = _event_inputs_with_known_car(n_events=20, car_value=0.0)
    t_stat, p_value, n = cross_sectional_t_test(cars)
    assert n == 20
    assert abs(t_stat) < 1.0
    assert p_value > 0.1


def test_cross_sectional_t_test_is_significant_under_a_real_strong_signal() -> None:
    _, _, cars = _event_inputs_with_known_car(n_events=20, car_value=0.05)
    t_stat, p_value, n = cross_sectional_t_test(cars)
    assert n == 20
    assert t_stat > 0
    assert p_value < 0.01


def test_bmp_test_null_vs_strong_signal() -> None:
    sar_null, _, _ = _event_inputs_with_known_car(n_events=20, car_value=0.0)
    stat_null, p_null, n_null = bmp_standardized_test(sar_null)
    assert n_null == 20
    assert abs(stat_null) < 1.0
    assert p_null > 0.1

    sar_signal, _, _ = _event_inputs_with_known_car(n_events=20, car_value=0.05)
    stat_signal, p_signal, n_signal = bmp_standardized_test(sar_signal)
    assert n_signal == 20
    assert stat_signal > 0
    assert p_signal < 0.01


def test_corrado_rank_test_null_vs_strong_signal() -> None:
    _, rank_null, _ = _event_inputs_with_known_car(n_events=20, car_value=0.0)
    stat_null, p_null, n_null = corrado_rank_test(rank_null)
    assert n_null == 20
    # Under a real null (no injected CAR), the event-window day's own
    # rank among its pooled estimation-window days is not
    # systematically higher or lower than the real null mean rank --
    # a small deviation either way, never the large one-directional
    # deviation the strong-signal case below produces.
    assert abs(stat_null) < 1.5

    _, rank_signal, _ = _event_inputs_with_known_car(n_events=20, car_value=0.05)
    stat_signal, p_signal, n_signal = corrado_rank_test(rank_signal)
    assert n_signal == 20
    assert stat_signal > 0
    assert p_signal < 0.05


def test_bmp_and_rank_tests_return_nan_with_fewer_than_two_real_events() -> None:
    sar_inputs, rank_inputs, _ = _event_inputs_with_known_car(n_events=1, car_value=0.05)
    stat, p, n = bmp_standardized_test(sar_inputs)
    assert n == 1
    assert stat != stat  # nan != nan
    assert p != p
    stat, p, n = corrado_rank_test(rank_inputs)
    assert n == 1
    assert stat != stat
    assert p != p


# --- Holm-Bonferroni ---------------------------------------------------------


def test_holm_bonferroni_hand_computed_example() -> None:
    """3 p-values, sorted ascending: 0.01, 0.02, 0.04. Holm multipliers
    are (3, 2, 1) applied in ascending order with a running max to
    enforce monotonicity: adjusted = max(0.03, 0.04, 0.04) = 0.03,
    0.04, 0.04."""
    raw = {"a": 0.04, "b": 0.01, "c": 0.02}
    adjusted = holm_bonferroni(raw)
    assert adjusted["b"] == pytest.approx(0.03)
    assert adjusted["c"] == pytest.approx(0.04)
    assert adjusted["a"] == pytest.approx(0.04)


def test_holm_bonferroni_passes_nan_through_untouched() -> None:
    raw = {"a": 0.01, "b": float("nan")}
    adjusted = holm_bonferroni(raw)
    assert adjusted["a"] == pytest.approx(0.01)
    assert adjusted["b"] != adjusted["b"]  # still nan


def test_holm_bonferroni_never_exceeds_one() -> None:
    raw = {"a": 0.9, "b": 0.8}
    adjusted = holm_bonferroni(raw)
    assert all(0.0 <= v <= 1.0 for v in adjusted.values())


# --- placebo determinism -----------------------------------------------------


def test_placebo_seed_is_deterministic_and_varies_with_each_input() -> None:
    s1 = placebo_seed("abc123", "event-1", 0)
    s2 = placebo_seed("abc123", "event-1", 0)
    assert s1 == s2  # same inputs -> same real seed, every time

    assert placebo_seed("abc123", "event-1", 1) != s1
    assert placebo_seed("abc123", "event-2", 0) != s1
    assert placebo_seed("xyz999", "event-1", 0) != s1


def test_run_placebo_is_deterministic_across_two_real_runs() -> None:
    company_days = TRADING_DAYS[:200]
    real_dates = [TRADING_DAYS[100]]

    def draw_fn(pseudo_date: dt.date) -> float | None:
        return float(pseudo_date.toordinal() % 7)

    run1 = run_placebo("spechash", "evt-1", company_days, real_dates, draw_fn, n_draws=50)
    run2 = run_placebo("spechash", "evt-1", company_days, real_dates, draw_fn, n_draws=50)
    assert run1 == run2
    assert len(run1) == 50


def test_run_placebo_excludes_dates_within_the_confounding_window_of_a_real_event() -> None:
    company_days = TRADING_DAYS[:60]
    real_event_date = TRADING_DAYS[30]

    seen_pseudo_dates: list[dt.date] = []

    def draw_fn(pseudo_date: dt.date) -> float | None:
        seen_pseudo_dates.append(pseudo_date)
        return 0.0

    run_placebo("spechash", "evt-1", company_days, [real_event_date], draw_fn, n_draws=200)
    assert seen_pseudo_dates  # the fixture must actually have eligible days
    for d in seen_pseudo_dates:
        assert abs((d - real_event_date).days) > CONFOUNDING_WINDOW_DAYS


def test_placebo_percentile_hand_computed() -> None:
    placebo_values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    # 7 of the 10 placebo values are strictly less than 7.5.
    assert placebo_percentile(7.5, placebo_values) == pytest.approx(70.0)


def test_placebo_percentile_returns_none_with_too_few_draws() -> None:
    assert placebo_percentile(5.0, [1.0, 2.0, 3.0]) is None


# --- CARE rating severity bands / transition direction ----------------------


def test_rating_transition_direction() -> None:
    assert rating_transition_direction(5, 10) == "downgrade"
    assert rating_transition_direction(10, 5) == "upgrade"
    assert rating_transition_direction(5, 5) is None


def test_downgrade_severity_bands() -> None:
    assert downgrade_severity_band(prev_ordinal=5, new_ordinal=8) == "within_investment_grade"
    assert (
        downgrade_severity_band(prev_ordinal=9, new_ordinal=10)
        == "crossing_into_sub_investment_grade"
    )
    assert downgrade_severity_band(prev_ordinal=15, new_ordinal=19) == "to_default_d"


# --- spec-hash freeze guard (real integration test against the live DB) ----


@pytest.mark.integration
def test_load_and_verify_spec_succeeds_for_a_matching_registered_hash(
    db_session: Session, tmp_path: object
) -> None:
    import hashlib
    import json
    from pathlib import Path

    spec_content = json.dumps({"spec_version": "test-v1", "n": 1})
    spec_path = Path(str(tmp_path)) / "spec.test-v1.json"
    spec_path.write_text(spec_content, encoding="utf-8")
    real_sha256 = hashlib.sha256(spec_path.read_bytes()).hexdigest()

    model_version = f"test-{uuid.uuid4().hex[:12]}"
    db_session.execute(
        text(
            "INSERT INTO model_registry (id, model_name, model_version, artifact_hash) "
            "VALUES (gen_random_uuid(), 'event-study-spec', :version, :hash)"
        ),
        {"version": model_version, "hash": real_sha256},
    )
    db_session.flush()

    spec = load_and_verify_spec(db_session, spec_path, model_version)
    assert spec.sha256 == real_sha256
    assert spec.raw["n"] == 1


@pytest.mark.integration
def test_load_and_verify_spec_refuses_a_spec_edited_after_freeze(
    db_session: Session, tmp_path: object
) -> None:
    import hashlib
    from pathlib import Path

    spec_path = Path(str(tmp_path)) / "spec.test-v2.json"
    spec_path.write_text('{"n": 1}', encoding="utf-8")
    frozen_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest()

    model_version = f"test-{uuid.uuid4().hex[:12]}"
    db_session.execute(
        text(
            "INSERT INTO model_registry (id, model_name, model_version, artifact_hash) "
            "VALUES (gen_random_uuid(), 'event-study-spec', :version, :hash)"
        ),
        {"version": model_version, "hash": frozen_hash},
    )
    db_session.flush()

    # Edit the spec file AFTER it was frozen -- the real violation this
    # guard exists to catch.
    spec_path.write_text('{"n": 2}', encoding="utf-8")

    with pytest.raises(ValueError, match="freeze guard"):
        load_and_verify_spec(db_session, spec_path, model_version)


@pytest.mark.integration
def test_load_and_verify_spec_refuses_an_unregistered_version(
    db_session: Session, tmp_path: object
) -> None:
    from pathlib import Path

    spec_path = Path(str(tmp_path)) / "spec.never-registered.json"
    spec_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="not registered"):
        load_and_verify_spec(db_session, spec_path, "never-registered-version")
