"""Phase 4 §10 `dossier-export` command: writes a real, already-
persisted dossier (§6 Markdown or JSON) to a real file."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.agent.export import export_dossier_json, export_dossier_markdown  # noqa: E402
from ledgerlight.agent.models import Dossier, Investigation  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.models import Company  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a real dossier to a file.")
    parser.add_argument("--investigation", required=True, help="real investigation_id (UUID)")
    parser.add_argument("--version", type=int, default=None, help="default: the latest version")
    parser.add_argument("--format", choices=["markdown", "json"], required=True)
    parser.add_argument("--out", required=True, help="output file path")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        investigation_id = uuid.UUID(args.investigation)
        investigation = session.get(Investigation, investigation_id)
        if investigation is None:
            print(f"no real investigation with id {investigation_id}")
            return 1

        query = select(Dossier).where(Dossier.investigation_id == investigation_id)
        query = (
            query.where(Dossier.version == args.version)
            if args.version is not None
            else query.order_by(Dossier.version.desc())
        )
        dossier = session.scalars(query).first()
        if dossier is None:
            print(f"no real dossier found for investigation {investigation_id}")
            return 1

        if args.format == "markdown":
            company = session.get(Company, investigation.company_id)
            company_name = (
                company.display_name if company is not None else str(investigation.company_id)
            )
            content = export_dossier_markdown(dossier, investigation, company_name)
        else:
            content = export_dossier_json(dossier, investigation)

    out_path = Path(args.out)
    out_path.write_text(content, encoding="utf-8")
    print(f"wrote {out_path} ({args.format}, dossier version {dossier.version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
