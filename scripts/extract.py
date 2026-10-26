"""Run structured extraction over every chunk the rules baseline
classifies as AUD_RESIGN (the one real worked extractor in Phase 2 --
see ledgerlight.knowledge.extraction's module docstring)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.knowledge.classifier import rules_baseline_predict  # noqa: E402
from ledgerlight.knowledge.extraction_pipeline import run_aud_resign_extraction  # noqa: E402
from ledgerlight.knowledge.models import Chunk  # noqa: E402


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)

    with session_factory() as session:
        chunks = session.scalars(select(Chunk).order_by(Chunk.id)).all()
        candidate_ids = [c.id for c in chunks if rules_baseline_predict(c.text) == "AUD_RESIGN"]
        print(f"chunks classified AUD_RESIGN by rules baseline: {len(candidate_ids)}")

        stats = run_aud_resign_extraction(session, candidate_ids)

    print(f"chunks_processed: {stats.chunks_processed}")
    print(f"chunks_already_extracted: {stats.chunks_already_extracted}")
    print(f"events_created: {stats.events_created}")
    print(f"fields_created: {stats.fields_created}")
    print(f"fields_failed_verification: {stats.fields_failed_verification}")
    print(f"review_items_created: {stats.review_items_created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
