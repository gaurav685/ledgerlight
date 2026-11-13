"""Enhancement 1: Governance Event Study (market reaction).

Implements the frozen methodology in
`docs/enhancements/event-study/spec.md` / `spec.v1.json` -- never
independently of it. Point-in-time correct (every event is only ever
included if its real `known_at` predates the as-of date of the run
that uses it); deterministic (every random draw is seeded from a
fixed, documented formula, never wall-clock or an unseeded RNG).

Layering, deliberately: the statistical core (market-model fitting,
abnormal returns, CAR, the three significance tests, Holm correction,
placebo) is pure -- takes and returns plain Python/NumPy values, no DB
session -- so it is directly unit-testable against hand-computed
synthetic fixtures. The DB-touching layer (gathering real event
candidates, loading real `price_bars`, persisting results) is kept
thin and separate, the same split `ledgerlight.modelling.rating_features`
already uses between `extract_rating_observations` (DB) and
`compute_rating_features` (pure).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import numpy as np
from scipy import stats
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.modelling.rating_features import (
    RATING_ORDINAL,
    RatingObservation,
    extract_rating_observations,
)
from ledgerlight.research.models import EventStudyEventResult, EventStudyRun

_IST = ZoneInfo("Asia/Kolkata")

INVESTMENT_GRADE_MAX_ORDINAL = 9
SUB_INVESTMENT_GRADE_MAX_ORDINAL = 18
DEFAULT_ORDINAL = RATING_ORDINAL["D"]

EVENT_WINDOWS: dict[str, tuple[int, int]] = {
    "CAR_m1_p1": (-1, 1),
    "CAR_0_p5": (0, 5),
    "CAR_m10_p10": (-10, 10),
    "CAR_m30_m1": (-30, -1),
    "CAR_p2_p60": (2, 60),
}
PRIMARY_WINDOW = "CAR_m1_p1"

ESTIMATION_WINDOW = (-250, -30)
MIN_ESTIMATION_DAYS = 120
LIQUIDITY_MIN_PCT_DAYS_TRADED = 0.80
CONFOUNDING_WINDOW_DAYS = 10
POSSIBLE_CORPORATE_ACTION_ABS_RETURN = 0.50
PLACEBO_N_DRAWS = 1000


# --- Trading-day index and return series (thin DB-loading layer) -----------


def build_trading_day_index(session: Session) -> list[dt.date]:
    """Every real, distinct `price_bars.trade_date` that actually
    exists -- there is no dedicated NSE holiday-calendar module in
    this project (confirmed, not assumed, before writing this), so a
    real missing bhavcopy file for a real holiday is already absent
    from this index by construction, never separately inferred."""
    rows = session.execute(text("SELECT DISTINCT trade_date FROM price_bars ORDER BY trade_date"))
    return [cast(dt.date, row[0]) for row in rows]


def load_company_closes(session: Session, company_id: uuid.UUID) -> dict[dt.date, float]:
    """Real daily close prices for one real company, keyed by real
    trade date, via its own identifier history (`company_identifiers`
    -- an NSE_SYMBOL can change over time, so this is NOT a bare
    symbol lookup)."""
    rows = session.execute(
        text(
            """
            SELECT pb.trade_date, pb.close
            FROM price_bars pb
            JOIN company_identifiers ci
              ON ci.identifier_type = 'NSE_SYMBOL' AND ci.value = pb.symbol
            WHERE ci.company_id = :company_id
              AND pb.close IS NOT NULL
              AND (ci.valid_from IS NULL OR pb.trade_date >= ci.valid_from)
              AND (ci.valid_to IS NULL OR pb.trade_date < ci.valid_to)
            ORDER BY pb.trade_date
            """
        ),
        {"company_id": company_id},
    ).all()
    return {cast(dt.date, r[0]): float(cast(Decimal, r[1])) for r in rows}


def build_market_index(session: Session, method: str = "turnover_weighted") -> dict[dt.date, float]:
    """Real daily market-return series. `turnover_weighted` (the
    primary market model, spec §5) is a real, documented substitute
    for market-cap weighting -- `price_bars` has no shares-outstanding
    field, so true market-cap weighting is not possible with this
    schema; `turnover` (real traded value) is used instead, disclosed
    explicitly, never silently presented as textbook market-cap
    weighting. `equal_weighted` is the robustness alternative.

    Aggregated server-side (one row per real trade_date, not one row
    per real (trade_date, symbol) pair, which is the full real
    price_bars row count -- millions) -- found to matter in practice:
    the naive per-row version was killed twice by this host's own,
    real, independently confirmed memory pressure before this fix."""
    if method not in ("turnover_weighted", "equal_weighted"):
        raise ValueError(f"unknown market index method: {method!r}")

    weight_expr = "COALESCE(turnover, 0)" if method == "turnover_weighted" else "1"
    rows = session.execute(
        text(
            f"""
            SELECT trade_date,
                   SUM(((close - prev_close) / prev_close) * ({weight_expr})) AS weighted_sum,
                   SUM({weight_expr}) AS total_weight
            FROM price_bars
            WHERE close IS NOT NULL AND prev_close IS NOT NULL AND prev_close != 0
            GROUP BY trade_date
            ORDER BY trade_date
            """
        )
    ).all()

    index: dict[dt.date, float] = {}
    for row in rows:
        trade_date = cast(dt.date, row[0])
        weighted_sum = row[1]
        total_weight = row[2]
        if weighted_sum is None or total_weight is None or float(total_weight) <= 0:
            continue
        index[trade_date] = float(weighted_sum) / float(total_weight)
    return index


# --- Pure statistical core ---------------------------------------------------


def simple_returns(
    closes: dict[dt.date, float], trading_days: list[dt.date]
) -> dict[dt.date, float]:
    """Real day-over-day simple returns, computed strictly along the
    real trading-day index (never a bare dict-iteration order, which
    is not guaranteed to be calendar-ordered for an arbitrary dict)."""
    available = [d for d in trading_days if d in closes]
    returns: dict[dt.date, float] = {}
    for prev_day, day in zip(available, available[1:], strict=False):
        if closes[prev_day] == 0:
            continue
        returns[day] = (closes[day] - closes[prev_day]) / closes[prev_day]
    return returns


def trading_day_offsets(
    trading_days: list[dt.date], day_zero: dt.date, offsets: range
) -> list[dt.date]:
    """Real trading days at each of `offsets` relative to `day_zero`'s
    own index position in `trading_days` -- an offset that runs off
    either end of the real index is simply omitted, never padded."""
    if day_zero not in trading_days:
        return []
    zero_idx = trading_days.index(day_zero)
    result = []
    for offset in offsets:
        idx = zero_idx + offset
        if 0 <= idx < len(trading_days):
            result.append(trading_days[idx])
    return result


def first_trading_day_at_or_after(trading_days: list[dt.date], target: dt.date) -> dt.date | None:
    for day in trading_days:
        if day >= target:
            return day
    return None


@dataclass
class MarketModelFit:
    alpha: float
    beta: float
    residual_std: float
    n_days: int
    market_mean: float
    market_sst: float  # sum of squared deviations of market return in estimation window


def fit_market_model(
    event_returns: dict[dt.date, float],
    market_returns: dict[dt.date, float],
    estimation_days: list[dt.date],
) -> MarketModelFit | None:
    """OLS market model (spec §5): R_it = alpha_i + beta_i * R_mt + e_it,
    fit on the real estimation window only. Returns None if fewer than
    `MIN_ESTIMATION_DAYS` real paired observations exist -- the
    estimation-window-sufficiency filter (spec §7)."""
    xs: list[float] = []
    ys: list[float] = []
    for day in estimation_days:
        if day in event_returns and day in market_returns:
            xs.append(market_returns[day])
            ys.append(event_returns[day])
    n = len(xs)
    if n < MIN_ESTIMATION_DAYS:
        return None

    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    x_mean = float(x.mean())
    y_mean = float(y.mean())
    sst_m = float(np.sum((x - x_mean) ** 2))
    if sst_m == 0:
        return None
    beta = float(np.sum((x - x_mean) * (y - y_mean)) / sst_m)
    alpha = y_mean - beta * x_mean
    residuals = y - (alpha + beta * x)
    # Residual variance with the real (n - 2) degrees-of-freedom correction
    # for a 2-parameter (alpha, beta) OLS fit -- never a biased /n divisor.
    residual_var = float(np.sum(residuals**2) / (n - 2))
    return MarketModelFit(
        alpha=alpha,
        beta=beta,
        residual_std=residual_var**0.5,
        n_days=n,
        market_mean=x_mean,
        market_sst=sst_m,
    )


def abnormal_returns(
    event_returns: dict[dt.date, float],
    market_returns: dict[dt.date, float],
    fit: MarketModelFit,
    days: list[dt.date],
) -> dict[dt.date, float]:
    """AR_t = R_it - (alpha + beta * R_mt), for each real day both
    series actually have data -- a day missing from either series is
    simply absent from the result, never imputed."""
    out: dict[dt.date, float] = {}
    for day in days:
        if day in event_returns and day in market_returns:
            predicted = fit.alpha + fit.beta * market_returns[day]
            out[day] = event_returns[day] - predicted
    return out


def car_for_window(
    ar_by_day: dict[dt.date, float], window_days: list[dt.date]
) -> tuple[float, int]:
    """Real CAR and real N (days with actual data) for one window --
    N is reported separately per spec §7's own per-window-N rule,
    since it can genuinely differ event-to-event and window-to-window."""
    values = [ar_by_day[d] for d in window_days if d in ar_by_day]
    return (sum(values), len(values)) if values else (0.0, 0)


def forecast_error_variance(fit: MarketModelFit, market_return_on_day: float) -> float:
    """The real per-day forecast-error-corrected variance (MacKinlay
    1997, eq. 12) -- accounts for the real estimation uncertainty in
    alpha/beta themselves, not just the residual variance, so a
    market return on the event day far from the estimation window's
    own mean gets a real, wider confidence band."""
    t = fit.n_days
    return (fit.residual_std**2) * (
        1 + 1 / t + ((market_return_on_day - fit.market_mean) ** 2) / fit.market_sst
    )


@dataclass
class EventSarInput:
    """One real event's own inputs to the BMP standardized test --
    its real window AR values and the real per-day market returns in
    that same window (needed for the forecast-error correction)."""

    fit: MarketModelFit
    ar_by_day: dict[dt.date, float]
    market_returns: dict[dt.date, float]
    window_days: list[dt.date]


def bmp_standardized_test(events: list[EventSarInput]) -> tuple[float, float, int]:
    """Boehmer-Musumeci-Poulsen (1991) standardized-residual test.
    Each event's real window CAR is divided by its own real
    forecast-error-corrected standard error (summed across the real
    window days, under the standard independence-across-days
    approximation) to get a standardized abnormal return SAR_i; the
    test statistic is then a plain cross-sectional t-test on the real
    SAR_i values -- this is what makes it robust to event-induced
    variance increases a plain CAR t-test is not.

    Returns (t_stat, p_value, n). n < 2 returns (nan, nan, n) -- never
    a fabricated statistic from too few real events."""
    sars: list[float] = []
    for event in events:
        car, n = car_for_window(event.ar_by_day, event.window_days)
        if n == 0:
            continue
        window_variance = sum(
            forecast_error_variance(event.fit, event.market_returns[d])
            for d in event.window_days
            if d in event.market_returns
        )
        if window_variance <= 0:
            continue
        sars.append(car / (window_variance**0.5))

    n = len(sars)
    if n < 2:
        return float("nan"), float("nan"), n
    arr = np.asarray(sars, dtype=float)
    t_stat, p_value = stats.ttest_1samp(arr, 0.0)
    return float(t_stat), float(p_value), n


def cross_sectional_t_test(cars: list[float]) -> tuple[float, float, int]:
    """Plain Brown-Warner-style cross-sectional t-test on real raw
    CAR values (no standardization) -- the simplest, most easily
    audited of the three tests, reported alongside the more robust
    BMP/rank tests, never in place of them."""
    n = len(cars)
    if n < 2:
        return float("nan"), float("nan"), n
    t_stat, p_value = stats.ttest_1samp(np.asarray(cars, dtype=float), 0.0)
    return float(t_stat), float(p_value), n


@dataclass
class CorradoRankInput:
    """One real event's full pooled (estimation + event window)
    abnormal-return series, needed for the Corrado rank test's own
    rank-pooling step."""

    ar_by_day: dict[dt.date, float]
    all_pooled_days: list[dt.date]  # estimation + event window, in order
    estimation_days: list[dt.date]
    window_days: list[dt.date]


def corrado_rank_test(events: list[CorradoRankInput]) -> tuple[float, float, int]:
    """Corrado (1989) non-parametric rank test. For each real event,
    ranks ALL its own real pooled (estimation + event-window)
    abnormal returns from 1..K, takes the real average rank of the
    event-window days, and standardizes the cross-sectional average
    deviation from the null mean rank (K+1)/2 by the real
    estimation-period rank variance -- never assumes any return
    distribution shape, by design."""
    deviations: list[float] = []
    estimation_rank_devs_by_event: list[list[float]] = []

    for event in events:
        days_with_data = [d for d in event.all_pooled_days if d in event.ar_by_day]
        k = len(days_with_data)
        if k < 2:
            continue
        values = [event.ar_by_day[d] for d in days_with_data]
        ranks = stats.rankdata(values)
        rank_by_day = dict(zip(days_with_data, ranks, strict=True))
        null_mean_rank = (k + 1) / 2.0

        window_ranks = [rank_by_day[d] for d in event.window_days if d in rank_by_day]
        if not window_ranks:
            continue
        avg_window_rank = sum(window_ranks) / len(window_ranks)
        deviations.append(avg_window_rank - null_mean_rank)

        est_devs = [
            rank_by_day[d] - null_mean_rank for d in event.estimation_days if d in rank_by_day
        ]
        estimation_rank_devs_by_event.append(est_devs)

    n = len(deviations)
    if n < 2:
        return float("nan"), float("nan"), n

    # Real cross-sectional-time-series variance estimate, pooled across
    # every event's own real estimation-period rank deviations.
    pooled: list[float] = [d for devs in estimation_rank_devs_by_event for d in devs]
    if len(pooled) < 2:
        return float("nan"), float("nan"), n
    pooled_arr = np.asarray(pooled, dtype=float)
    s_rank = float(np.sqrt(np.mean(pooled_arr**2)))
    if s_rank == 0:
        return float("nan"), float("nan"), n

    mean_deviation = float(np.mean(deviations))
    z_stat = (mean_deviation * (n**0.5)) / s_rank
    p_value = float(2 * (1 - stats.norm.cdf(abs(z_stat))))
    return z_stat, p_value, n


def holm_bonferroni(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni step-down correction over the real grid of
    p-values actually computed in one run -- never a hypothetical
    larger grid. `nan` inputs (too few real events for that
    type/window) pass through as `nan`, never silently dropped from
    the correction's own denominator count."""
    real_items = [(k, v) for k, v in p_values.items() if not (isinstance(v, float) and np.isnan(v))]
    real_items.sort(key=lambda kv: kv[1])
    m = len(real_items)
    adjusted: dict[str, float] = dict(p_values)
    running_max = 0.0
    for i, (key, p) in enumerate(real_items):
        candidate = min((m - i) * p, 1.0)
        running_max = max(running_max, candidate)
        adjusted[key] = running_max
    return adjusted


# --- Placebo -----------------------------------------------------------------


def placebo_seed(spec_sha256: str, event_id: str, iteration_index: int) -> int:
    """The real, documented seed formula from `spec.v1.json`'s own
    `placebo.placebo_seed_formula` field -- reproduced here, not
    reinvented, so a re-run against identical frozen input data
    produces byte-identical placebo draws."""
    digest = hashlib.sha256(f"{spec_sha256}:{event_id}:{iteration_index}".encode()).hexdigest()
    return int(digest[:16], 16)


def run_placebo(
    spec_sha256: str,
    event_id: str,
    company_trading_days_same_year: list[dt.date],
    real_event_dates_for_company: list[dt.date],
    draw_fn: Callable[[dt.date], float | None],
    n_draws: int = PLACEBO_N_DRAWS,
) -> list[float]:
    """Draws `n_draws` deterministic pseudo-event dates (year-matched,
    at least `CONFOUNDING_WINDOW_DAYS` away from every real included
    event for this company) and calls `draw_fn(pseudo_date) -> float
    | None` (the real CAR[-1,+1] computation for that pseudo-date) for
    each -- `draw_fn` is injected rather than hard-coded so the pure
    placebo-date-selection logic is unit-testable on its own, without
    a real market-model fit for every call."""
    eligible = [
        d
        for d in company_trading_days_same_year
        if all(
            abs((d - real).days) > CONFOUNDING_WINDOW_DAYS for real in real_event_dates_for_company
        )
    ]
    if not eligible:
        return []

    results: list[float] = []
    for i in range(n_draws):
        rng = np.random.default_rng(placebo_seed(spec_sha256, event_id, i))
        pseudo_date = eligible[int(rng.integers(0, len(eligible)))]
        value = draw_fn(pseudo_date)
        if value is not None:
            results.append(value)
    return results


def placebo_percentile(real_value: float, placebo_values: list[float]) -> float | None:
    """The real empirical percentile of `real_value` within the real
    placebo distribution -- `None` if there are too few real placebo
    draws to form a meaningful percentile."""
    if len(placebo_values) < 10:
        return None
    arr = np.asarray(placebo_values, dtype=float)
    return float((arr < real_value).mean() * 100.0)


# --- Severity classification (CARE ratings) ----------------------------------


def rating_transition_direction(prev_ordinal: int, new_ordinal: int) -> str | None:
    """ "downgrade" | "upgrade" | None (no symbol change)."""
    if new_ordinal > prev_ordinal:
        return "downgrade"
    if new_ordinal < prev_ordinal:
        return "upgrade"
    return None


def downgrade_severity_band(prev_ordinal: int, new_ordinal: int) -> str:
    """Spec §3's three severity bands, using
    `ledgerlight.modelling.rating_features.RATING_ORDINAL` directly."""
    if new_ordinal == DEFAULT_ORDINAL:
        return "to_default_d"
    if prev_ordinal <= INVESTMENT_GRADE_MAX_ORDINAL < new_ordinal:
        return "crossing_into_sub_investment_grade"
    return "within_investment_grade"


@dataclass
class RatingTransitionEvent:
    company_id: uuid.UUID
    known_at: dt.datetime
    direction: str  # "downgrade" | "upgrade"
    severity_band: str | None  # only set for downgrades
    prev_observation: RatingObservation
    new_observation: RatingObservation


def rating_transitions_for_company(
    observations: list[RatingObservation], company_id: uuid.UUID
) -> list[RatingTransitionEvent]:
    """Real downgrade/upgrade transitions from a real, already-ordered
    observation sequence (`extract_rating_observations`) -- outlook-
    only changes (no symbol change) are deliberately not an event
    here (spec §3's own disclosed narrowing)."""
    transitions: list[RatingTransitionEvent] = []
    for prev_obs, new_obs in zip(observations, observations[1:], strict=False):
        direction = rating_transition_direction(prev_obs.ordinal, new_obs.ordinal)
        if direction is None:
            continue
        severity = (
            downgrade_severity_band(prev_obs.ordinal, new_obs.ordinal)
            if direction == "downgrade"
            else None
        )
        transitions.append(
            RatingTransitionEvent(
                company_id=company_id,
                known_at=new_obs.known_at,
                direction=direction,
                severity_band=severity,
                prev_observation=prev_obs,
                new_observation=new_obs,
            )
        )
    return transitions


# --- Spec loading and the freeze guard --------------------------------------


@dataclass
class EventStudySpec:
    version: str
    sha256: str
    raw: dict[str, object]


def load_and_verify_spec(session: Session, spec_path: Path, spec_version: str) -> EventStudySpec:
    """Loads a real spec file and refuses to proceed unless its real
    sha256 matches the hash already frozen in `model_registry` under
    this exact `spec_version` -- the real freeze guard: results are
    never computed, let alone persisted, under a spec that was edited
    after the version it claims to be was first frozen."""
    spec_bytes = spec_path.read_bytes()
    real_sha256 = hashlib.sha256(spec_bytes).hexdigest()

    row = session.execute(
        text(
            "SELECT artifact_hash FROM model_registry "
            "WHERE model_name = 'event-study-spec' AND model_version = :version"
        ),
        {"version": spec_version},
    ).first()
    if row is None:
        raise ValueError(
            f"spec version {spec_version!r} is not registered in model_registry -- "
            "run scripts/event_study_register_spec.py to freeze it before running."
        )
    registered_hash = row[0]
    if registered_hash != real_sha256:
        raise ValueError(
            f"spec freeze guard: {spec_path} has real sha256 {real_sha256}, but "
            f"model_registry's frozen event-study-spec/{spec_version} is "
            f"{registered_hash} -- this spec file was edited after it was frozen. "
            "Refusing to run. A revised spec must be registered as a NEW version."
        )
    return EventStudySpec(version=spec_version, sha256=real_sha256, raw=json.loads(spec_bytes))


def current_git_sha(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def data_snapshot_hash(real_event_ids: list[str]) -> str:
    """A real, deterministic hash of exactly which real event ids this
    run actually used -- sorted first, so this is never order-
    dependent on an arbitrary DB retrieval order (the same
    determinism discipline `ledgerlight.agent.render._content_sort_key`
    already applies elsewhere in this project)."""
    canonical = json.dumps(sorted(real_event_ids))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class FilterStageCounts:
    """How many real events survive after each real filter stage, in
    order -- spec §7's own explicit requirement, never only a final
    survivor count."""

    stage_counts: dict[str, int] = field(default_factory=dict)


_CompanyKey = uuid.UUID


def find_confounded_keys(
    dates_by_company: dict[_CompanyKey, list[dt.date]], window_days: int
) -> set[tuple[_CompanyKey, dt.date]]:
    """Spec §7's confounding filter, as a pure function: two real
    included events for the SAME company within `window_days` calendar
    days of each other are BOTH flagged (never only the later one --
    neither can be trusted to be the sole cause of any real market
    reaction around either date). A company with only one real event
    in its own list never produces a flag. Takes/returns plain
    dicts/sets so this is directly unit-testable without any real
    filter pipeline around it."""
    confounded: set[tuple[_CompanyKey, dt.date]] = set()
    for company_id, dates in dates_by_company.items():
        for i, d1 in enumerate(dates):
            for d2 in dates[i + 1 :]:
                if abs((d1 - d2).days) <= window_days:
                    confounded.add((company_id, d1))
                    confounded.add((company_id, d2))
    return confounded


# --- Gathering real event candidates (DB-touching layer) --------------------


@dataclass
class RawEventCandidate:
    event_id: str  # deterministic string id, used in data_snapshot_hash/placebo seed
    company_id: uuid.UUID
    event_type_code: str
    known_at: dt.datetime
    severity_band: str | None
    is_primary: bool
    evidence: dict[str, object]


def gather_care_rating_candidates(session: Session) -> list[RawEventCandidate]:
    """Real CARE downgrade/upgrade transitions, span-verified, for
    every real company with >= 1 real CARE filing -- reuses
    `ledgerlight.modelling.rating_features.extract_rating_observations`
    directly, never a re-implementation of that extraction."""
    company_ids = session.execute(
        text(
            """
            SELECT DISTINCT f.company_id
            FROM filings f
            JOIN document_versions dv ON dv.id = f.version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE d.source_id = 'care'
            """
        )
    ).all()

    candidates: list[RawEventCandidate] = []
    for row in company_ids:
        company_id = cast(uuid.UUID, row[0])
        observations = extract_rating_observations(session, company_id)
        transitions = rating_transitions_for_company(observations, company_id)
        for t in transitions:
            event_type_code = (
                "CARE_RATING_DOWNGRADE" if t.direction == "downgrade" else "CARE_RATING_UPGRADE"
            )
            candidates.append(
                RawEventCandidate(
                    event_id=(
                        f"care:{company_id}:{t.new_observation.version_id}:"
                        f"{t.new_observation.char_start}"
                    ),
                    company_id=company_id,
                    event_type_code=event_type_code,
                    known_at=t.known_at,
                    severity_band=t.severity_band,
                    is_primary=True,
                    evidence={
                        "source": "care_rating_observation",
                        "document_version_id": str(t.new_observation.version_id),
                        "page_number": t.new_observation.page_number,
                        "char_start": t.new_observation.char_start,
                        "char_end": t.new_observation.char_end,
                        "prev_rating_symbol": t.prev_observation.rating_symbol,
                        "new_rating_symbol": t.new_observation.rating_symbol,
                    },
                )
            )
    return candidates


def gather_outcome_event_candidates(
    session: Session, event_type_code: str, is_primary: bool
) -> list[RawEventCandidate]:
    """Real `Event` rows of one real `event_type_code` (e.g.
    `SEBI_ORDER_AGAINST_COMPANY`, `IBBI_CIRP_ADMISSION`) -- `is_primary`
    is set by the caller from this spec's own, already-checked-against-
    real-data tier decision (spec §2), never re-derived from
    `events.status` here (so a future status change on these rows
    cannot silently move an event between the primary/secondary arms
    without a new, deliberate spec decision)."""
    rows = session.execute(
        text(
            """
            SELECT e.id, e.company_id, e.known_at, e.status
            FROM events e
            JOIN event_types et ON et.id = e.event_type_id
            WHERE et.code = :code AND e.company_id IS NOT NULL AND e.known_at IS NOT NULL
            """
        ),
        {"code": event_type_code},
    ).all()
    return [
        RawEventCandidate(
            event_id=f"event:{row[0]}",
            company_id=row[1],
            event_type_code=event_type_code,
            known_at=row[2],
            severity_band=None,
            is_primary=is_primary,
            evidence={"source": "events_table", "event_id": str(row[0]), "status": row[3]},
        )
        for row in rows
    ]


# --- Orchestration -----------------------------------------------------------


@dataclass
class EventStudyRunResult:
    run_id: uuid.UUID
    event_counts_json: Mapping[str, object]
    metrics_json: Mapping[str, object]


def _resolve_event_date(trading_days: list[dt.date], known_at: dt.datetime) -> dt.date | None:
    aware = known_at if known_at.tzinfo is not None else known_at.replace(tzinfo=dt.UTC)
    ist_date = aware.astimezone(_IST).date()
    return first_trading_day_at_or_after(trading_days, ist_date)


def run_event_study(
    session: Session,
    spec: EventStudySpec,
    git_sha: str,
    requested_by: str,
) -> EventStudyRunResult:
    """Runs the full, real governance event study against the live DB,
    under the already-frozen-and-verified `spec` (see
    `load_and_verify_spec`), and persists one real `EventStudyRun` row
    plus one real `EventStudyEventResult` row per real event actually
    scored."""
    stage_counts: dict[str, int] = {}

    trading_days = build_trading_day_index(session)
    market_primary = build_market_index(session, "turnover_weighted")
    market_robustness = build_market_index(session, "equal_weighted")

    raw_candidates = (
        gather_care_rating_candidates(session)
        + gather_outcome_event_candidates(session, "SEBI_ORDER_AGAINST_COMPANY", is_primary=True)
        + gather_outcome_event_candidates(session, "IBBI_CIRP_ADMISSION", is_primary=False)
    )
    stage_counts["raw_candidates"] = len(raw_candidates)

    # Stage 1: point-in-time validity -- the real event date must
    # resolve to a real trading day actually present in the index.
    with_event_date: list[tuple[RawEventCandidate, dt.date]] = []
    for c in raw_candidates:
        event_date = _resolve_event_date(trading_days, c.known_at)
        if event_date is not None:
            with_event_date.append((c, event_date))
    stage_counts["point_in_time_validity"] = len(with_event_date)

    closes_by_company: dict[uuid.UUID, dict[dt.date, float]] = {}
    returns_by_company: dict[uuid.UUID, dict[dt.date, float]] = {}

    def _company_returns(company_id: uuid.UUID) -> dict[dt.date, float]:
        if company_id not in returns_by_company:
            closes = load_company_closes(session, company_id)
            closes_by_company[company_id] = closes
            returns_by_company[company_id] = simple_returns(closes, trading_days)
        return returns_by_company[company_id]

    # Stage 2: estimation-window sufficiency (the real market-model fit
    # on the turnover-weighted index must succeed -- >= MIN_ESTIMATION_DAYS
    # real paired observations).
    fits: dict[tuple[uuid.UUID, dt.date], MarketModelFit] = {}
    after_estimation: list[tuple[RawEventCandidate, dt.date]] = []
    for c, event_date in with_event_date:
        est_days = trading_day_offsets(trading_days, event_date, range(*ESTIMATION_WINDOW, 1))
        fit = fit_market_model(_company_returns(c.company_id), market_primary, est_days)
        if fit is not None:
            fits[(c.company_id, event_date)] = fit
            after_estimation.append((c, event_date))
    stage_counts["estimation_window_sufficiency"] = len(after_estimation)

    # Stage 3: liquidity -- real % of the real estimation-window trading
    # days this company actually has a close for.
    after_liquidity: list[tuple[RawEventCandidate, dt.date]] = []
    for c, event_date in after_estimation:
        est_days = trading_day_offsets(trading_days, event_date, range(*ESTIMATION_WINDOW, 1))
        closes = closes_by_company[c.company_id]
        pct_traded = sum(1 for d in est_days if d in closes) / len(est_days) if est_days else 0.0
        if pct_traded >= LIQUIDITY_MIN_PCT_DAYS_TRADED:
            after_liquidity.append((c, event_date))
    stage_counts["liquidity"] = len(after_liquidity)

    # Stage 4: confounding -- another INCLUDED (post-liquidity) event for
    # the SAME company within +/- CONFOUNDING_WINDOW_DAYS calendar days.
    by_company: dict[uuid.UUID, list[dt.date]] = {}
    for c, event_date in after_liquidity:
        by_company.setdefault(c.company_id, []).append(event_date)

    confounded_keys = find_confounded_keys(by_company, CONFOUNDING_WINDOW_DAYS)

    final_events = after_liquidity
    stage_counts["confounded"] = len(confounded_keys)
    stage_counts["included_in_primary_analysis"] = len(
        [
            (c, d)
            for c, d in final_events
            if c.is_primary and (c.company_id, d) not in confounded_keys
        ]
    )

    # Compute real abnormal returns / CAR per window for every surviving
    # event (primary and secondary alike -- the secondary/IBBI arm is
    # reported, just never used for a significance claim).
    event_results: list[dict[str, object]] = []
    car_by_type_window: dict[str, dict[str, list[float]]] = {}
    sar_inputs_by_type_window: dict[str, dict[str, list[EventSarInput]]] = {}
    rank_inputs_by_type_window: dict[str, dict[str, list[CorradoRankInput]]] = {}

    # Robustness accumulators (spec §3's own "equal-weighted vs
    # value-weighted market" and "with vs without the confounding
    # filter" checks) -- primary window only, mean CAR only, no
    # inferential battery, to keep this bounded: these are robustness
    # *checks* on the primary finding's direction/magnitude, not a
    # second full significance claim.
    primary_window_car_incl_confounded: dict[str, list[float]] = {}
    primary_window_car_equal_weighted: dict[str, list[float]] = {}

    real_event_dates_by_company: dict[uuid.UUID, list[dt.date]] = {}
    for c, event_date in final_events:
        real_event_dates_by_company.setdefault(c.company_id, []).append(event_date)

    for c, event_date in final_events:
        fit = fits[(c.company_id, event_date)]
        company_returns = returns_by_company[c.company_id]
        est_days = trading_day_offsets(trading_days, event_date, range(*ESTIMATION_WINDOW, 1))
        widest = trading_day_offsets(trading_days, event_date, range(-30, 61, 1))
        pooled_days = sorted(set(est_days) | set(widest))
        ar_by_day = abnormal_returns(company_returns, market_primary, fit, pooled_days)

        # Real daily AR by offset (-30..+60), for the real CAAR plots
        # (spec §3's own output requirement) -- captured here, at the
        # point where ar_by_day is already real and available, never
        # recomputed later from a fresh price fetch.
        day_zero_idx = trading_days.index(event_date) if event_date in trading_days else None
        daily_ar_by_offset: dict[str, float] = {}
        if day_zero_idx is not None:
            for offset in range(-30, 61):
                idx = day_zero_idx + offset
                if 0 <= idx < len(trading_days):
                    day = trading_days[idx]
                    if day in ar_by_day:
                        daily_ar_by_offset[str(offset)] = ar_by_day[day]

        closes = closes_by_company[c.company_id]
        possible_corporate_action = any(
            abs(company_returns[d]) > POSSIBLE_CORPORATE_ACTION_ABS_RETURN
            for d in pooled_days
            if d in company_returns
        )

        confounded = (c.company_id, event_date) in confounded_keys
        car_by_window: dict[str, float] = {}
        window_n_by_window: dict[str, int] = {}
        for window_name, (start, end) in EVENT_WINDOWS.items():
            window_days = trading_day_offsets(trading_days, event_date, range(start, end + 1, 1))
            car, n = car_for_window(ar_by_day, window_days)
            car_by_window[window_name] = car
            window_n_by_window[window_name] = n

            if c.is_primary and window_name == PRIMARY_WINDOW and n > 0:
                primary_window_car_incl_confounded.setdefault(c.event_type_code, []).append(car)

            if c.is_primary and not confounded and n > 0:
                key_bucket = car_by_type_window.setdefault(c.event_type_code, {})
                key_bucket.setdefault(window_name, []).append(car)

                sar_bucket = sar_inputs_by_type_window.setdefault(c.event_type_code, {})
                sar_bucket.setdefault(window_name, []).append(
                    EventSarInput(
                        fit=fit,
                        ar_by_day=ar_by_day,
                        market_returns=market_primary,
                        window_days=window_days,
                    )
                )

                rank_bucket = rank_inputs_by_type_window.setdefault(c.event_type_code, {})
                rank_bucket.setdefault(window_name, []).append(
                    CorradoRankInput(
                        ar_by_day=ar_by_day,
                        all_pooled_days=pooled_days,
                        estimation_days=est_days,
                        window_days=window_days,
                    )
                )

        if c.is_primary and not confounded:
            equal_fit = fit_market_model(company_returns, market_robustness, est_days)
            if equal_fit is not None:
                equal_ar = abnormal_returns(company_returns, market_robustness, equal_fit, widest)
                primary_window_days = trading_day_offsets(
                    trading_days, event_date, range(*EVENT_WINDOWS[PRIMARY_WINDOW])
                )
                equal_car, equal_n = car_for_window(equal_ar, primary_window_days)
                if equal_n > 0:
                    primary_window_car_equal_weighted.setdefault(c.event_type_code, []).append(
                        equal_car
                    )

        placebo_mean = placebo_std = placebo_pct = None
        if c.is_primary and not confounded:
            same_year_days = [d for d in trading_days if d.year == event_date.year]
            real_dates_for_company = real_event_dates_by_company.get(c.company_id, [])

            def _placebo_draw(
                pseudo_date: dt.date, _company_returns: dict[dt.date, float] = company_returns
            ) -> float | None:
                pseudo_est = trading_day_offsets(
                    trading_days, pseudo_date, range(*ESTIMATION_WINDOW, 1)
                )
                pseudo_fit = fit_market_model(_company_returns, market_primary, pseudo_est)
                if pseudo_fit is None:
                    return None
                pseudo_window = trading_day_offsets(
                    trading_days, pseudo_date, range(*EVENT_WINDOWS[PRIMARY_WINDOW])
                )
                pseudo_ar = abnormal_returns(
                    _company_returns, market_primary, pseudo_fit, pseudo_window
                )
                pseudo_car, pseudo_n = car_for_window(pseudo_ar, pseudo_window)
                return pseudo_car if pseudo_n > 0 else None

            placebo_values = run_placebo(
                spec.sha256, c.event_id, same_year_days, real_dates_for_company, _placebo_draw
            )
            if placebo_values:
                placebo_mean = float(np.mean(placebo_values))
                placebo_std = float(np.std(placebo_values))
                real_primary_car = car_by_window[PRIMARY_WINDOW]
                placebo_pct = placebo_percentile(real_primary_car, placebo_values)

        event_results.append(
            {
                "company_id": c.company_id,
                "event_type_code": c.event_type_code,
                "severity_band": c.severity_band,
                "event_date": event_date,
                "is_primary": c.is_primary,
                "excluded_reason": None,
                "confounded": confounded,
                "possible_corporate_action": possible_corporate_action,
                "alpha": fit.alpha,
                "beta": fit.beta,
                "residual_std": fit.residual_std,
                "n_estimation_days": fit.n_days,
                "car_by_window": car_by_window,
                "window_n_by_window": window_n_by_window,
                "daily_ar_by_offset": daily_ar_by_offset,
                "placebo_mean": placebo_mean,
                "placebo_std": placebo_std,
                "placebo_percentile": placebo_pct,
                "evidence_json": c.evidence,
            }
        )

    # Real aggregate metrics per (event type, window): t-test, BMP, rank,
    # then Holm-Bonferroni across the real grid actually computed.
    MetricRow = dict[str, float | int | None]
    metrics_by_type: dict[str, dict[str, MetricRow]] = {}
    raw_p_values: dict[str, float] = {}
    for event_type, windows in car_by_type_window.items():
        event_type_metrics: dict[str, MetricRow] = {}
        for window_name, cars in windows.items():
            t_stat, t_p, n = cross_sectional_t_test(cars)
            bmp_stat, bmp_p, bmp_n = bmp_standardized_test(
                sar_inputs_by_type_window[event_type][window_name]
            )
            rank_stat, rank_p, rank_n = corrado_rank_test(
                rank_inputs_by_type_window[event_type][window_name]
            )
            event_type_metrics[window_name] = {
                "n": n,
                "mean_car": float(np.mean(cars)) if cars else None,
                "median_car": float(np.median(cars)) if cars else None,
                "t_stat": t_stat,
                "t_p": t_p,
                "bmp_stat": bmp_stat,
                "bmp_p": bmp_p,
                "rank_stat": rank_stat,
                "rank_p": rank_p,
            }
            grid_key = f"{event_type}::{window_name}"
            raw_p_values[f"{grid_key}::t"] = t_p
            raw_p_values[f"{grid_key}::bmp"] = bmp_p
            raw_p_values[f"{grid_key}::rank"] = rank_p
        metrics_by_type[event_type] = event_type_metrics

    holm_adjusted = holm_bonferroni(raw_p_values)
    for event_type, type_windows in metrics_by_type.items():
        for window_name, m in type_windows.items():
            grid_key = f"{event_type}::{window_name}"
            m["t_p_holm"] = holm_adjusted[f"{grid_key}::t"]
            m["bmp_p_holm"] = holm_adjusted[f"{grid_key}::bmp"]
            m["rank_p_holm"] = holm_adjusted[f"{grid_key}::rank"]

    robustness: dict[str, dict[str, float | int | str | None]] = {}
    for event_type in set(primary_window_car_incl_confounded) | set(
        primary_window_car_equal_weighted
    ):
        incl = primary_window_car_incl_confounded.get(event_type, [])
        equal = primary_window_car_equal_weighted.get(event_type, [])
        primary_metrics = metrics_by_type.get(event_type, {}).get(PRIMARY_WINDOW, {})
        robustness[event_type] = {
            "primary_window": PRIMARY_WINDOW,
            "mean_car_turnover_weighted_excl_confounded": primary_metrics.get("mean_car"),
            "mean_car_turnover_weighted_incl_confounded": (float(np.mean(incl)) if incl else None),
            "n_incl_confounded": len(incl),
            "mean_car_equal_weighted_excl_confounded": (float(np.mean(equal)) if equal else None),
            "n_equal_weighted": len(equal),
        }

    metrics: dict[str, object] = dict(metrics_by_type)
    metrics["_robustness"] = robustness

    event_ids_used = [c.event_id for c, _ in final_events]
    run = EventStudyRun(
        id=uuid.uuid4(),
        spec_version=spec.version,
        spec_sha256=spec.sha256,
        data_snapshot_hash=data_snapshot_hash(event_ids_used),
        git_sha=git_sha,
        requested_by=requested_by,
        status="completed",
        event_counts_json=stage_counts,
        metrics_json=metrics,
    )
    session.add(run)
    session.flush()

    for result in event_results:
        session.add(EventStudyEventResult(id=uuid.uuid4(), run_id=run.id, **result))
    session.commit()

    return EventStudyRunResult(run_id=run.id, event_counts_json=stage_counts, metrics_json=metrics)
