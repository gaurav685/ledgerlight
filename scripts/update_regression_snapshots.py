"""Phase 6A §4: regenerate tests/fixtures/regression_snapshots.json from
the real, current database state for the exact same frozen subjects
`tests/test_regression_snapshots.py` already points at (same company
ids, same as_of dates, same investigation/dossier, same model name and
version) -- this script never picks new subjects itself.

This must be run deliberately, never silently: it requires --confirm,
and refuses to run unless you also pass --reason, a short note on WHY
the golden file is changing (a real pipeline change, a frozen-data
correction, etc.) -- printed to stdout so it ends up in your own commit
message. After running it, also add an entry to
docs/phase-6/evidence/sec04-regression-snapshots.md explaining the
real change, and re-run `make test-regression` to confirm the new
golden file is now self-consistent.

Usage:
    python3 -m uv run python scripts/update_regression_snapshots.py \\
        --confirm --reason "re-ran features-build after a real fix to X"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from ledgerlight.agent.export import export_dossier_markdown  # noqa: E402
from ledgerlight.agent.models import Dossier, Investigation  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Company  # noqa: E402

GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "regression_snapshots.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the golden regression-snapshot fixture from real current data."
    )
    parser.add_argument(
        "--confirm", action="store_true", help="required -- refuses to run without it"
    )
    parser.add_argument(
        "--reason", required=True, help="short note on why the golden file is changing"
    )
    args = parser.parse_args()

    if not args.confirm:
        print("Refusing to update the golden regression-snapshot file without --confirm.")
        print("This file is read by every regression test -- changing it without a real,")
        print("documented reason hides real regressions. Re-run with --confirm --reason '...'.")
        return 1

    old = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    settings = load_settings()
    session_factory = make_session_factory(settings)
    new: dict[str, object] = {"_comment": old["_comment"]}

    with session_factory() as session:
        ext = old["extraction"]
        rows = session.execute(
            text(
                "SELECT ef.value_json, ef.validation_status, e.status, e.severity, "
                "e.detector_name, e.detector_version "
                "FROM event_fields ef JOIN events e ON e.id = ef.event_id "
                "WHERE e.company_id = :cid AND ef.field_name = :field "
                "ORDER BY ef.value_json, e.detector_version, ef.id"
            ),
            {"cid": ext["company_id"], "field": ext["field_name"]},
        ).fetchall()
        new["extraction"] = {
            "company_id": ext["company_id"],
            "company_name": ext["company_name"],
            "field_name": ext["field_name"],
            "records": [
                {
                    "value_json": r[0],
                    "validation_status": r[1],
                    "event_status": r[2],
                    "event_severity": r[3],
                    "detector_name": r[4],
                    "detector_version": r[5],
                }
                for r in rows
            ],
        }

        evt = old["events_and_tiers"]
        rows = session.execute(
            text(
                "SELECT et.code, e.status, e.severity, count(*) "
                "FROM events e JOIN event_types et ON et.id = e.event_type_id "
                "WHERE e.company_id = :cid "
                "GROUP BY et.code, e.status, e.severity ORDER BY et.code, e.status, e.severity"
            ),
            {"cid": evt["company_id"]},
        ).fetchall()
        new["events_and_tiers"] = {
            "company_id": evt["company_id"],
            "company_name": evt["company_name"],
            "by_type_status_severity": [
                {"event_type_code": r[0], "status": r[1], "severity": r[2], "count": r[3]}
                for r in rows
            ],
        }

        ent = old["entity_links"]
        rows = session.execute(
            text(
                "SELECT method, score, status FROM entity_links "
                "WHERE entity_id = :eid ORDER BY method, score"
            ),
            {"eid": ent["entity_id"]},
        ).fetchall()
        new["entity_links"] = {
            "entity_id": ent["entity_id"],
            "entity_display_name": ent["entity_display_name"],
            "entity_type": ent["entity_type"],
            "records": [{"method": r[0], "score": r[1], "status": r[2]} for r in rows],
        }

        feat = old["feature_values"]
        rows = session.execute(
            text(
                "SELECT feature_set_version, values FROM feature_snapshots "
                "WHERE company_id = :cid AND as_of = :as_of"
            ),
            {"cid": feat["company_id"], "as_of": feat["as_of"]},
        ).fetchall()
        new["feature_values"] = {
            "company_id": feat["company_id"],
            "company_name": feat["company_name"],
            "as_of": feat["as_of"],
            "by_feature_set_version": {r[0]: r[1] for r in rows},
        }

        sc = old["score"]
        row = session.execute(
            text(
                "SELECT calibrated_probability, raw_probability, percentile, outcome_spec_hash "
                "FROM scores WHERE company_id = :cid AND as_of = :as_of "
                "AND model_name = :model_name AND model_version = :model_version"
            ),
            {
                "cid": sc["company_id"],
                "as_of": sc["as_of"],
                "model_name": sc["model_name"],
                "model_version": sc["model_version"],
            },
        ).first()
        if row is None:
            print(f"ERROR: no real score found for the frozen subject {sc['company_name']}")
            return 1
        new["score"] = {
            "company_id": sc["company_id"],
            "company_name": sc["company_name"],
            "as_of": sc["as_of"],
            "model_name": sc["model_name"],
            "model_version": sc["model_version"],
            "calibrated_probability": row[0],
            "raw_probability": row[1],
            "percentile": row[2],
            "outcome_spec_hash": row[3],
        }

        doss = old["dossier"]
        investigation = session.get(Investigation, uuid.UUID(doss["investigation_id"]))
        dossier = session.get(Dossier, uuid.UUID(doss["dossier_id"]))
        if investigation is None or dossier is None:
            print(f"ERROR: the frozen investigation/dossier {doss['investigation_id']} is gone")
            return 1
        company = session.get(Company, investigation.company_id)
        company_name = company.display_name if company is not None else doss["company_name"]
        markdown = export_dossier_markdown(dossier, investigation, company_name)
        new["dossier"] = {
            "investigation_id": doss["investigation_id"],
            "dossier_id": doss["dossier_id"],
            "company_name": company_name,
            "as_of": doss["as_of"],
            "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
        }

    GOLDEN_PATH.write_text(json.dumps(new, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Updated {GOLDEN_PATH} -- reason: {args.reason}")
    print("Now add a dated entry to docs/phase-6/evidence/sec04-regression-snapshots.md")
    print("explaining this change, and re-run `make test-regression`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
