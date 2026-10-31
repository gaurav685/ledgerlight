"""Phase 3 Sec4.3 (part 1): build SEED-track governance features --
"descriptive only" per the brief, for the 15 SEED-track companies.
See `ledgerlight/modelling/seed_governance_features.py` for the real
disclosed caveats this carries (near-all-CANDIDATE tier; investor-
relations-sourced events' known_at clustering).

Reuses the exact (company_id, as_of) grid already built by
`scripts/build_feature_snapshots.py`'s price-liquidity-1.0 pass, scoped
to SEED-track companies only (those with a real NSE_SYMBOL or BSE_SCRIP
identifying them as a SEED-track company, per
`ledgerlight.ingestion.seed_track`), as feature_set_version
`seed-governance-1.0`.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.seed_track import SEED_COMPANY_SEARCH_NAMES  # noqa: E402
from ledgerlight.modelling.seed_governance_features import (  # noqa: E402
    GOVERNANCE_EVENT_CODES,
    compute_governance_features,
    load_governance_events,
)

FEATURE_SET_VERSION = "seed-governance-1.0"

_AS_OF_SEMANTICS = (
    "Same monthly as_of grid as price-liquidity-1.0, scoped to SEED-track companies. "
    "Counts real Event rows (status in candidate/verified) with known_at <= as_of, "
    "trailing 12 months. GUIDANCE_MISS excluded (Sec5's own feature)."
)


def _ensure_feature_definitions(session: Any) -> None:
    for code in GOVERNANCE_EVENT_CODES:
        for tier, provenance in (("candidate", "EVENT_CANDIDATE"), ("verified", "VERIFIED")):
            name = f"{code.lower()}_{tier}_count_12m"
            session.execute(
                text(
                    "INSERT INTO feature_definitions "
                    "(id, name, version, description, inputs, provenance_tier, "
                    " as_of_semantics, lookback_days, track) "
                    "VALUES (:id, :name, :version, :description, :inputs, :tier, "
                    " :as_of_semantics, 365, 'SEED') "
                    "ON CONFLICT (name, version) DO NOTHING"
                ),
                {
                    "id": uuid.uuid4(),
                    "name": name,
                    "version": FEATURE_SET_VERSION,
                    "description": (
                        f"Real count of {code} events ({tier} tier), trailing 12 months."
                    ),
                    "inputs": '["events", "event_types"]',
                    "tier": provenance,
                    "as_of_semantics": _AS_OF_SEMANTICS,
                },
            )
    session.commit()


def _seed_track_company_ids(session: Any) -> dict[uuid.UUID, str]:
    symbols = [
        identifiers.nse_symbol
        for _name, identifiers in SEED_COMPANY_SEARCH_NAMES
        if identifiers.nse_symbol
    ]
    rows = session.execute(
        text(
            "SELECT DISTINCT company_id, value FROM company_identifiers "
            "WHERE identifier_type = 'NSE_SYMBOL' AND value = ANY(:symbols)"
        ),
        {"symbols": symbols},
    ).all()
    return {row[0]: row[1] for row in rows}


def _load_universe_grid(session: Any, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Any]]:
    rows = session.execute(
        text(
            "SELECT company_id, as_of FROM feature_snapshots "
            "WHERE feature_set_version = 'price-liquidity-1.0' "
            "AND company_id = ANY(:ids) "
            "ORDER BY company_id, as_of"
        ),
        {"ids": company_ids},
    ).all()
    grid: dict[uuid.UUID, list[Any]] = {}
    for company_id, as_of in rows:
        grid.setdefault(company_id, []).append(as_of)
    return grid


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        _ensure_feature_definitions(session)
        seed_companies = _seed_track_company_ids(session)
        grid = _load_universe_grid(session, list(seed_companies.keys()))

        total_snapshots = 0
        companies_processed = 0

        for company_id, as_of_dates in grid.items():
            events = load_governance_events(session, company_id)
            companies_processed += 1

            for as_of in as_of_dates:
                values = compute_governance_features(events, as_of)
                known_at_values = [e.known_at for e in events if e.known_at.date() <= as_of]
                max_input_known_at = max(known_at_values) if known_at_values else None
                _upsert_snapshot(session, company_id, as_of, values, max_input_known_at)
                total_snapshots += 1

            session.commit()

    print(f"seed_companies_matched: {len(seed_companies)}")
    print(f"companies_processed: {companies_processed}")
    print(f"feature_snapshots_written: {total_snapshots}")
    return 0


def _upsert_snapshot(
    session: Any,
    company_id: uuid.UUID,
    as_of: Any,
    values: dict[str, int],
    max_input_known_at: Any,
) -> None:
    import json

    session.execute(
        text(
            "INSERT INTO feature_snapshots "
            "(id, company_id, as_of, feature_set_version, values, "
            " max_input_known_at, data_quality_flags) "
            "VALUES (:id, :company_id, :as_of, :feature_set_version, "
            " CAST(:values AS JSONB), :max_input_known_at, CAST('[]' AS JSONB)) "
            "ON CONFLICT (company_id, as_of, feature_set_version) "
            "DO UPDATE SET values = EXCLUDED.values, "
            "max_input_known_at = EXCLUDED.max_input_known_at"
        ),
        {
            "id": uuid.uuid4(),
            "company_id": company_id,
            "as_of": as_of,
            "feature_set_version": FEATURE_SET_VERSION,
            "values": json.dumps(values),
            "max_input_known_at": max_input_known_at,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
