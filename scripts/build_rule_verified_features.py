"""Phase 3 Sec4.2: build the UNIVERSE track's RULE-VERIFIED features --
per the brief: "ratings: counts of actions, downgrades and negative
watches/outlooks, the current rating bucket, time since the last
downgrade" and "prior SEBI orders and prior IBBI-related mentions, via
auto-links." See `ledgerlight/modelling/rating_features.py` for the
real, span-verified rating-symbol extraction this is built on -- NOT
the Phase 2 zero-shot RATING_ACT detector, which is EVENT-CANDIDATE
tier, per the brief's own feature policy.

Reuses the exact (company_id, as_of) grid already built by
`scripts/build_feature_snapshots.py`'s price-liquidity-1.0 pass, as a
separate `feature_set_version` ("rule-verified-1.0") -- so UNIVERSE
membership for this feature group stays identical to Sec4.1's (a
company trading that period's bhavcopy), without re-deriving it.

Real, disclosed coverage limitation: a CARE document dated before a
company's real NSE listing date cannot resolve via NSE-symbol-based
auto-linking at all -- there is no NSE symbol yet to assign. This
affects several real pre-IPO CARE press releases (e.g. PNB Housing
Finance's 2003-2016 documents, predating its real 2016-11-07 listing;
Gensol Engineering's March-2023 document, predating its 2023-07-05
listing) -- see `docs/phase-3/evidence/link-filings-run-post-sec3
-broadening.log`'s `unresolved` list. Not a bug: there is no real NSE
symbol to link those documents to.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.modelling.rating_features import (  # noqa: E402
    compute_rating_features,
    count_prior_filings,
    extract_rating_observations,
)

FEATURE_SET_VERSION = "rule-verified-1.0"

FEATURE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "rating_actions_count_12m",
        "lookback_days": 365,
        "description": (
            "Count of real, span-verified CARE rating observations in the trailing " "12 months."
        ),
    },
    {
        "name": "downgrades_count_12m",
        "lookback_days": 365,
        "description": (
            "Count of real rating-ordinal downgrades (new grade worse than the prior "
            "observation) in the trailing 12 months."
        ),
    },
    {
        "name": "current_rating_ordinal",
        "lookback_days": None,
        "description": (
            "Ordinal of the latest known CARE long-term grade as of as_of "
            "(0=AAA best, 19=D worst); None if never rated."
        ),
    },
    {
        "name": "days_since_last_downgrade",
        "lookback_days": None,
        "description": "Real calendar days since the most recent known downgrade; None if none.",
    },
    {
        "name": "negative_outlook_flag",
        "lookback_days": None,
        "description": (
            "1 if the latest rating observation's own evidence text mentions a "
            "negative outlook/watch, else 0; None if never rated."
        ),
    },
    {
        "name": "prior_sebi_orders_count",
        "lookback_days": None,
        "description": "Real count of auto-linked SEBI order Filing rows known as of as_of.",
    },
    {
        "name": "prior_ibbi_mentions_count",
        "lookback_days": None,
        "description": "Real count of auto-linked IBBI order Filing rows known as of as_of.",
    },
]

_AS_OF_SEMANTICS = (
    "Same monthly as_of grid as price-liquidity-1.0. Rating features use only "
    "CARE rating observations with known_at <= as_of; prior-filing counts use only "
    "Filing rows whose document known_at <= as_of."
)


def _ensure_feature_definitions(session: Any) -> None:
    for fd in FEATURE_DEFINITIONS:
        session.execute(
            text(
                "INSERT INTO feature_definitions "
                "(id, name, version, description, inputs, provenance_tier, "
                " as_of_semantics, lookback_days, track) "
                "VALUES (:id, :name, :version, :description, :inputs, 'RULE_VERIFIED', "
                " :as_of_semantics, :lookback_days, 'UNIVERSE') "
                "ON CONFLICT (name, version) DO NOTHING"
            ),
            {
                "id": uuid.uuid4(),
                "name": fd["name"],
                "version": FEATURE_SET_VERSION,
                "description": fd["description"],
                "inputs": '["document_pages.raw_text (care)", "filings"]',
                "as_of_semantics": _AS_OF_SEMANTICS,
                "lookback_days": fd["lookback_days"],
            },
        )
    session.commit()


def _load_universe_grid(session: Any) -> dict[uuid.UUID, list[dt.date]]:
    rows = session.execute(
        text(
            "SELECT company_id, as_of FROM feature_snapshots "
            "WHERE feature_set_version = 'price-liquidity-1.0' "
            "AND company_id IN (SELECT DISTINCT company_id FROM filings) "
            "ORDER BY company_id, as_of"
        )
    ).all()
    grid: dict[uuid.UUID, list[dt.date]] = {}
    for company_id, as_of in rows:
        grid.setdefault(company_id, []).append(as_of)
    return grid


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        _ensure_feature_definitions(session)
        grid = _load_universe_grid(session)

        total_snapshots = 0
        companies_processed = 0

        for company_id, as_of_dates in grid.items():
            rating_observations = extract_rating_observations(session, company_id)
            companies_processed += 1

            for as_of in as_of_dates:
                rating = compute_rating_features(rating_observations, as_of)
                sebi_known_at = _max_filing_known_at(session, company_id, "sebi", as_of)
                ibbi_known_at = _max_filing_known_at(session, company_id, "ibbi", as_of)
                values = {
                    "rating_actions_count_12m": rating.rating_actions_count_12m,
                    "downgrades_count_12m": rating.downgrades_count_12m,
                    "current_rating_ordinal": rating.current_rating_ordinal,
                    "days_since_last_downgrade": rating.days_since_last_downgrade,
                    "negative_outlook_flag": rating.negative_outlook_flag,
                    "prior_sebi_orders_count": count_prior_filings(
                        session, company_id, "sebi", as_of
                    ),
                    "prior_ibbi_mentions_count": count_prior_filings(
                        session, company_id, "ibbi", as_of
                    ),
                }
                flags = []
                if rating.current_rating_ordinal is None:
                    flags.append("no_care_rating_observed_as_of")
                elif rating.days_since_last_downgrade is None:
                    flags.append("no_downgrade_observed_yet")
                rating_known_at = [
                    o.known_at for o in rating_observations if o.known_at.date() <= as_of
                ]
                candidates = [
                    k for k in (sebi_known_at, ibbi_known_at, *rating_known_at) if k is not None
                ]
                max_input_known_at = max(candidates) if candidates else None
                _upsert_snapshot(session, company_id, as_of, values, flags, max_input_known_at)
                total_snapshots += 1

            session.commit()

    print(f"companies_processed: {companies_processed}")
    print(f"feature_snapshots_written: {total_snapshots}")
    return 0


def _max_filing_known_at(
    session: Any, company_id: uuid.UUID, source_id: str, as_of: dt.date
) -> dt.datetime | None:
    result = session.execute(
        text(
            """
            SELECT max(dv.known_at) FROM filings f
            JOIN document_versions dv ON dv.id = f.version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE f.company_id = :company_id AND d.source_id = :source_id
              AND dv.known_at <= :as_of
            """
        ),
        {"company_id": company_id, "source_id": source_id, "as_of": as_of},
    ).scalar()
    return cast(dt.datetime | None, result)


def _upsert_snapshot(
    session: Any,
    company_id: uuid.UUID,
    as_of: dt.date,
    values: dict[str, Any],
    flags: list[str],
    max_input_known_at: dt.datetime | None,
) -> None:
    import json

    session.execute(
        text(
            "INSERT INTO feature_snapshots "
            "(id, company_id, as_of, feature_set_version, values, "
            " max_input_known_at, data_quality_flags) "
            "VALUES (:id, :company_id, :as_of, :feature_set_version, "
            " CAST(:values AS JSONB), :max_input_known_at, CAST(:flags AS JSONB)) "
            "ON CONFLICT (company_id, as_of, feature_set_version) "
            "DO UPDATE SET values = EXCLUDED.values, "
            "max_input_known_at = EXCLUDED.max_input_known_at, "
            "data_quality_flags = EXCLUDED.data_quality_flags"
        ),
        {
            "id": uuid.uuid4(),
            "company_id": company_id,
            "as_of": as_of,
            "feature_set_version": FEATURE_SET_VERSION,
            "values": json.dumps(values),
            "max_input_known_at": max_input_known_at,
            "flags": json.dumps(flags),
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
