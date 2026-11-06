"""Phase 6A §3: a reproducible, standalone script for the full real
pipeline (ingestion -> dossier), distinct from
`tests/test_e2e_pipeline.py`'s automated assertions. Calls the exact
same real production functions each of this project's other
`scripts/*.py` entrypoints calls -- nothing reimplemented, nothing
mocked. Safe to run repeatedly: every stage is independently
idempotent (confirmed by direct code inspection and by the automated
test's own `test_full_pipeline_runs_twice_without_duplicating_anything`).

Usage:
    python3 -m uv run --extra ocr python scripts/e2e_pipeline_demo.py \\
        --company-name "Demo Co" --as-of 2026-03-20

Steps run: import-local -> storage -> pages -> chunk -> embed ->
classify+extract+verify -> entity links -> feature/score lookup ->
investigation+dossier.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from ledgerlight.acquisition.import_local import import_inbox  # noqa: E402
from ledgerlight.agent.state_machine import run_investigation  # noqa: E402
from ledgerlight.agent.tools import get_risk_score  # noqa: E402
from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.models import Document, DocumentVersion  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402
from ledgerlight.ingestion.backfill_from_manifest import run_store_backfill  # noqa: E402
from ledgerlight.knowledge.chunking import chunk_version  # noqa: E402
from ledgerlight.knowledge.classifier import rules_baseline_predict  # noqa: E402
from ledgerlight.knowledge.embedding import (  # noqa: E402
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    embed_texts,
)
from ledgerlight.knowledge.entity_bootstrap import bootstrap_audit_firm_entities  # noqa: E402
from ledgerlight.knowledge.extraction_pipeline import run_aud_resign_extraction  # noqa: E402
from ledgerlight.knowledge.models import Chunk, Company, Event, EventField, Filing  # noqa: E402
from ledgerlight.processing.document_processor import process_version  # noqa: E402
from ledgerlight.processing.limits import ProcessingLimits  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402


def _document_html(seed_name: str) -> str:
    # import-local dedups purely on content sha256 (see its own
    # docstring) -- embedding seed_name makes each demo run's content
    # genuinely new, so it is a real new document each time rather than
    # a real duplicate-skip of the prior run's identical bytes.
    return f"""<html><body>
<!-- {seed_name} -->
<p>Notice is hereby given that KPMG, the Statutory Auditor of the
Company, has tendered its resignation effective March 15, 2026, due
to pre-occupation with other professional assignments. The Board
places on record its appreciation for the services rendered by the
outgoing auditor.</p>
</body></html>"""


def _drop_in_inbox(data_dir: Path, seed_name: str) -> None:
    inbox_dir = data_dir / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    file_path = inbox_dir / f"{seed_name}.html"
    file_path.write_text(_document_html(seed_name), encoding="utf-8")

    provenance_path = inbox_dir / "provenance.csv"
    file_existed = provenance_path.exists()
    with provenance_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if not file_existed:
            writer.writerow(["file_name", "original_url", "retrieved_at_by_user", "notes"])
        writer.writerow(
            [
                file_path.name,
                f"https://example.com/test-filing/{seed_name}",
                dt.date.today().isoformat(),
                "Phase 6A §3 reproducible e2e pipeline demo",
            ]
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the real ingestion -> dossier pipeline on one demo document."
    )
    parser.add_argument(
        "--company-id", default=None, help="existing company_id; omit to create one"
    )
    parser.add_argument("--company-name", default=None, help="name for a new company (if creating)")
    parser.add_argument("--as-of", default="2026-03-20", help="YYYY-MM-DD for score/investigation")
    args = parser.parse_args()

    settings = load_settings()
    session_factory = make_session_factory(settings)
    as_of = dt.date.fromisoformat(args.as_of)
    seed_name = f"e2e-demo-{uuid.uuid4().hex[:8]}"

    with session_factory() as session:
        if args.company_id:
            company_id = uuid.UUID(args.company_id)
        else:
            company = Company(display_name=args.company_name or f"E2E Demo Co {seed_name}")
            session.add(company)
            session.flush()
            session.commit()
            company_id = company.id
        print(f"company_id: {company_id}")

        # --- 1. import-local ----------------------------------------------
        _drop_in_inbox(settings.data_dir, seed_name)
        import_result = import_inbox(data_dir=settings.data_dir)
        print(
            f"import-local: imported={import_result.imported} "
            f"skipped_duplicate={import_result.skipped_duplicate}"
        )

        # --- 2. storage -----------------------------------------------------
        store = ObjectStore(settings)
        manifest_path = settings.data_dir / "manifests" / "manual.jsonl"
        backfill_stats = run_store_backfill(session, store, [manifest_path])
        session.commit()
        print(
            f"storage: documents_created={backfill_stats.documents_created} "
            f"versions_created={backfill_stats.versions_created}"
        )

        version = session.scalar(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.source_key.like(f"%{seed_name}%"))
        )
        if version is None:
            print("ERROR: no real document_version was created by store-backfill")
            return 1

        # --- 3. pages ---------------------------------------------------
        body = store.get(version.object_key)
        process_version(session, body, version, ProcessingLimits())
        session.commit()

        existing_filing = session.scalar(
            select(Filing).where(Filing.version_id == version.id, Filing.company_id == company_id)
        )
        if existing_filing is None:
            session.add(
                Filing(
                    version_id=version.id,
                    company_id=company_id,
                    link_method="manual",
                    confidence=1.0,
                )
            )
            session.commit()

        # --- 4. chunk -----------------------------------------------------
        chunk_version(session, version)
        session.commit()
        chunks = session.scalars(select(Chunk).where(Chunk.version_id == version.id)).all()
        print(f"chunk: chunks={len(chunks)}")

        # --- 5. embed -------------------------------------------------------
        unembedded = [c for c in chunks if c.embedding is None]
        if unembedded:
            vectors = embed_texts([c.text for c in unembedded])
            for chunk, vector in zip(unembedded, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model_name = EMBEDDING_MODEL_NAME
                chunk.embedding_model_version = EMBEDDING_MODEL_VERSION
            session.commit()
        print(f"embed: embedded={len(unembedded)}")

        # --- 6. classify + extract + verify -------------------------------
        candidate_ids = [c.id for c in chunks if rules_baseline_predict(c.text) == "AUD_RESIGN"]
        extraction_stats = run_aud_resign_extraction(session, candidate_ids)
        session.commit()
        print(
            f"extract: candidates={len(candidate_ids)} "
            f"events_created={extraction_stats.events_created} "
            f"fields_created={extraction_stats.fields_created}"
        )

        audit_firm_field = session.scalar(
            select(EventField).where(
                EventField.evidence_version_id == version.id, EventField.field_name == "audit_firm"
            )
        )
        if audit_firm_field is not None:
            event = session.get(Event, audit_firm_field.event_id)
            print(
                f"verify: audit_firm field validation_status={audit_firm_field.validation_status} "
                f"event_status={event.status if event else None}"
            )

        # --- 7/8. entity links --------------------------------------------
        entity_stats = bootstrap_audit_firm_entities(session)
        session.commit()
        print(
            f"entity links: audit_firm_entities_created={entity_stats.audit_firm_entities_created}"
        )

        # --- 9. feature snapshot + score -----------------------------------
        score_envelope = get_risk_score(session, company_id, as_of)
        print(f"score: found={score_envelope.data.found}")

        # --- 10. investigation + dossier -----------------------------------
        outcome = run_investigation(session, company_id, as_of, requested_by="e2e-pipeline-demo")
        session.commit()
        print(
            f"investigation_id: {outcome.investigation.id} "
            f"state: {outcome.investigation.state} "
            f"final_status: {outcome.investigation.final_status}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
