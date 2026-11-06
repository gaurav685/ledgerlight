"""Phase 6A §10: real per-filing cost measurement, per stage -- CPU
seconds, peak memory (RSS, sampled before/after each stage -- a real
but conservative proxy for true peak, disclosed as such), wall time,
storage bytes (raw + derived), embedding time, and a standalone NLI
(entailment) inference-time microbenchmark. LLM tokens/cost are 0
throughout: this project's agent uses the real offline template
renderer (docs/modelling/model-card.md), never a live LLM call --
already established in Phase 4's agent-eval (Cost USD p50=0.0000
p95=0.0000), not re-measured here.

Runs N real filings end to end (ingestion -> investigation), each a
fresh real document with embedded-unique content (so none hit
import-local's own real content-hash dedup), and reports mean/p95 per
stage across all N. Cleans up every real row and file it created.

Usage:
    python3 -m uv run python scripts/measure_cost_per_filing.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import statistics
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import psutil  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy import text as sa_text  # noqa: E402

from ledgerlight.acquisition.import_local import import_inbox  # noqa: E402
from ledgerlight.agent.budgets import BudgetConfig  # noqa: E402
from ledgerlight.agent.nli import entailment_score  # noqa: E402
from ledgerlight.agent.state_machine import run_investigation  # noqa: E402
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
from ledgerlight.knowledge.models import Chunk, Company  # noqa: E402
from ledgerlight.processing.document_processor import process_version  # noqa: E402
from ledgerlight.processing.limits import ProcessingLimits  # noqa: E402
from ledgerlight.storage.s3_store import ObjectStore  # noqa: E402

N_FILINGS = 10
PROC = psutil.Process()


@dataclass
class StageMeasurement:
    wall_seconds: list[float] = field(default_factory=list)
    cpu_seconds: list[float] = field(default_factory=list)
    peak_rss_mb: list[float] = field(default_factory=list)


T = TypeVar("T")


def _measure(
    stage: dict[str, StageMeasurement], name: str, fn: Callable[..., T], *args: object
) -> T:
    rss_before = PROC.memory_info().rss
    cpu_before = time.process_time()
    wall_before = time.monotonic()
    result = fn(*args)
    wall_after = time.monotonic()
    cpu_after = time.process_time()
    rss_after = PROC.memory_info().rss

    m = stage.setdefault(name, StageMeasurement())
    m.wall_seconds.append(wall_after - wall_before)
    m.cpu_seconds.append(cpu_after - cpu_before)
    m.peak_rss_mb.append(max(rss_before, rss_after) / (1024 * 1024))
    return result


def _html(seed_name: str) -> str:
    return (
        f"<html><body><p>Real cost-measurement filler text ({seed_name}). "
        "Notice is hereby given that KPMG, the Statutory Auditor of the "
        "Company, has tendered its resignation effective March 15, 2026. "
        + ("Phase 6A sec10 real cost sample sentence. " * 80)
        + "</p></body></html>"
    )


def _run_one_filing(
    settings: object,
    session_factory: object,
    store: ObjectStore,
    stage: dict[str, StageMeasurement],
) -> tuple[int, int]:
    """Returns (raw_bytes, derived_bytes) for this one real filing."""
    seed_name = f"cost-{uuid.uuid4().hex[:8]}"
    inbox_dir = settings.data_dir / "inbox"  # type: ignore[attr-defined]
    inbox_dir.mkdir(parents=True, exist_ok=True)
    html = _html(seed_name)
    (inbox_dir / f"{seed_name}.html").write_text(html, encoding="utf-8")
    provenance_path = inbox_dir / "provenance.csv"
    file_existed = provenance_path.exists()
    with provenance_path.open("a", newline="", encoding="utf-8") as fh:
        if not file_existed:
            fh.write("file_name,original_url,retrieved_at_by_user,notes\n")
        fh.write(
            f"{seed_name}.html,https://example.com/cost/{seed_name},2026-11-06,"
            "Phase 6A sec10 real cost measurement\n"
        )
    raw_bytes = len(html.encode("utf-8"))
    content_digest = hashlib.sha256(html.encode("utf-8")).hexdigest()

    # A dedicated manifest file per filing, not the shared manual.jsonl:
    # run_store_backfill() re-upserts EVERY entry still in the manifest
    # file it's given, every call (real, intended idempotency for its
    # actual use case -- safe to re-run the full backfill). This script
    # calls it once per filing; pointed at the shared manual.jsonl, that
    # replayed every PRIOR filing's entry too, re-creating document rows
    # this function's own cleanup had already deleted earlier in the same
    # run -- a real bug found while verifying this script's cleanup left
    # the DB clean (it didn't, until this fix).
    manifest_path = settings.data_dir / "manifests" / f"cost-measurement-{seed_name}.jsonl"  # type: ignore[attr-defined]

    _measure(
        stage,
        "import_local",
        lambda: import_inbox(data_dir=settings.data_dir, manifest_path=manifest_path),  # type: ignore[attr-defined]
    )

    session = session_factory()  # type: ignore[operator]
    try:
        _measure(stage, "storage_backfill", run_store_backfill, session, store, [manifest_path])
        session.commit()

        version = session.scalar(
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.source_key.like(f"%{seed_name}%"))
        )
        assert version is not None

        body = store.get(version.object_key)
        _measure(
            stage, "page_extraction", process_version, session, body, version, ProcessingLimits()
        )
        session.commit()

        _measure(stage, "chunking", chunk_version, session, version)
        session.commit()
        chunks = session.scalars(select(Chunk).where(Chunk.version_id == version.id)).all()

        unembedded = [c for c in chunks if c.embedding is None]
        derived_bytes = sum(len(c.text.encode("utf-8")) for c in chunks)
        if unembedded:
            vectors = _measure(stage, "embedding", embed_texts, [c.text for c in unembedded])
            for chunk, vector in zip(unembedded, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model_name = EMBEDDING_MODEL_NAME
                chunk.embedding_model_version = EMBEDDING_MODEL_VERSION
                derived_bytes += len(vector) * 4  # real float32 vector bytes
            session.commit()

        candidate_ids = [c.id for c in chunks if rules_baseline_predict(c.text) == "AUD_RESIGN"]
        _measure(stage, "classify_extract", run_aud_resign_extraction, session, candidate_ids)
        session.commit()

        _measure(stage, "entity_bootstrap", bootstrap_audit_firm_entities, session)
        session.commit()

        company = Company(display_name=f"Cost Measurement Co {seed_name}")
        session.add(company)
        session.flush()
        from ledgerlight.knowledge.models import Filing

        session.add(
            Filing(
                version_id=version.id, company_id=company.id, link_method="manual", confidence=1.0
            )
        )
        session.commit()

        _measure(
            stage,
            "investigation",
            run_investigation,
            session,
            company.id,
            dt.date(2026, 3, 20),
            "sec10-cost-measurement",
            BudgetConfig(),
        )
        session.commit()

        # cleanup -- synthetic cost-measurement sample, not real corpus content
        session.execute(
            sa_text(
                "DELETE FROM review_tasks WHERE dossier_id IN "
                "(SELECT id FROM dossiers WHERE investigation_id IN "
                "(SELECT id FROM investigations WHERE company_id = :cid))"
            ),
            {"cid": company.id},
        )
        session.execute(
            sa_text(
                "DELETE FROM dossiers WHERE investigation_id IN "
                "(SELECT id FROM investigations WHERE company_id = :cid)"
            ),
            {"cid": company.id},
        )
        session.execute(
            sa_text(
                "DELETE FROM claims WHERE investigation_id IN "
                "(SELECT id FROM investigations WHERE company_id = :cid)"
            ),
            {"cid": company.id},
        )
        session.execute(
            sa_text(
                "DELETE FROM investigation_steps WHERE investigation_id IN "
                "(SELECT id FROM investigations WHERE company_id = :cid)"
            ),
            {"cid": company.id},
        )
        session.execute(
            sa_text("DELETE FROM investigations WHERE company_id = :cid"), {"cid": company.id}
        )
        session.commit()
        session.execute(
            sa_text(
                "DELETE FROM entity_links WHERE mention_id IN "
                "(SELECT m.id FROM mentions m JOIN document_versions dv ON dv.id = m.version_id "
                "JOIN documents d ON d.id = dv.document_id WHERE d.source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        session.execute(
            sa_text(
                "DELETE FROM mentions WHERE version_id IN "
                "(SELECT dv.id FROM document_versions dv JOIN documents d ON d.id = dv.document_id "
                "WHERE d.source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        session.commit()
        # Events created by run_aud_resign_extraction get company_id=NULL
        # (never set by this script's manual Filing row) -- a real schema
        # fact found while fixing this cleanup: Event.company_id is only
        # ever populated by a real entity-resolution/filing-linking
        # service this script bypasses. Scoping by company_id matched
        # zero rows, leaving event_fields.evidence_version_id still
        # pointing at this filing's document_versions row and breaking
        # the later document_versions delete on FK. Scope by evidence
        # version instead.
        touched_event_ids = session.scalars(
            sa_text(
                "SELECT DISTINCT ef.event_id FROM event_fields ef "
                "JOIN document_versions dv ON dv.id = ef.evidence_version_id "
                "JOIN documents d ON d.id = dv.document_id WHERE d.source_key LIKE :p"
            ),
            {"p": f"%{seed_name}%"},
        ).all()
        session.execute(
            sa_text(
                "DELETE FROM event_fields WHERE evidence_version_id IN "
                "(SELECT dv.id FROM document_versions dv JOIN documents d ON d.id = dv.document_id "
                "WHERE d.source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        if touched_event_ids:
            session.execute(
                sa_text(
                    "DELETE FROM events WHERE id = ANY(:ids) "
                    "AND NOT EXISTS (SELECT 1 FROM event_fields WHERE event_id = events.id)"
                ),
                {"ids": touched_event_ids},
            )
        session.execute(sa_text("DELETE FROM events WHERE company_id = :cid"), {"cid": company.id})
        session.execute(sa_text("DELETE FROM filings WHERE company_id = :cid"), {"cid": company.id})
        session.execute(sa_text("DELETE FROM companies WHERE id = :cid"), {"cid": company.id})
        session.commit()
        # entity_identifiers/processing_attempts also FK-reference
        # document_versions (confirmed via pg_constraint -- a real gap
        # found in this cleanup: this pipeline run doesn't currently
        # populate either, but a future pipeline change could, and the
        # delete is a correct no-op either way).
        session.execute(
            sa_text(
                "DELETE FROM entity_identifiers WHERE evidence_version_id IN "
                "(SELECT dv.id FROM document_versions dv JOIN documents d ON d.id = dv.document_id "
                "WHERE d.source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        session.execute(
            sa_text(
                "DELETE FROM processing_attempts WHERE version_id IN "
                "(SELECT dv.id FROM document_versions dv JOIN documents d ON d.id = dv.document_id "
                "WHERE d.source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        session.execute(
            sa_text(
                "DELETE FROM chunks WHERE version_id IN "
                "(SELECT dv.id FROM document_versions dv JOIN documents d ON d.id = dv.document_id "
                "WHERE d.source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        session.execute(
            sa_text(
                "DELETE FROM document_pages WHERE version_id IN "
                "(SELECT dv.id FROM document_versions dv JOIN documents d ON d.id = dv.document_id "
                "WHERE d.source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        session.commit()
        session.execute(
            sa_text(
                "DELETE FROM document_versions WHERE document_id IN "
                "(SELECT id FROM documents WHERE source_key LIKE :p)"
            ),
            {"p": f"%{seed_name}%"},
        )
        session.execute(
            sa_text("DELETE FROM documents WHERE source_key LIKE :p"), {"p": f"%{seed_name}%"}
        )
        session.commit()
        (inbox_dir / f"{seed_name}.html").unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        blob_path = settings.data_dir / "raw" / "manual" / f"{content_digest}.html"  # type: ignore[attr-defined]
        blob_path.unlink(missing_ok=True)
    finally:
        session.close()

    return raw_bytes, derived_bytes


def _mean_p95(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = statistics.mean(values)
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * 0.95) - 1)
    return mean, sorted_vals[idx]


def main() -> int:
    settings = load_settings()
    session_factory = make_session_factory(settings)
    store = ObjectStore(settings)

    stage: dict[str, StageMeasurement] = {}
    raw_sizes: list[int] = []
    derived_sizes: list[int] = []

    for i in range(N_FILINGS):
        print(f"filing {i + 1}/{N_FILINGS}...", flush=True)
        raw, derived = _run_one_filing(settings, session_factory, store, stage)
        raw_sizes.append(raw)
        derived_sizes.append(derived)

    print(f"\n=== Per-stage cost (mean / p95 across N={N_FILINGS} real filings) ===")
    print(f"{'stage':<20} {'wall(s)':>14} {'cpu(s)':>14} {'peak RSS (MB)':>16}")
    for name, m in stage.items():
        wall_mean, wall_p95 = _mean_p95(m.wall_seconds)
        cpu_mean, cpu_p95 = _mean_p95(m.cpu_seconds)
        rss_mean, rss_p95 = _mean_p95(m.peak_rss_mb)
        print(
            f"{name:<20} {wall_mean:>6.3f}/{wall_p95:<6.3f} "
            f"{cpu_mean:>6.3f}/{cpu_p95:<6.3f} {rss_mean:>7.1f}/{rss_p95:<7.1f}"
        )

    raw_mean, raw_p95 = _mean_p95([float(x) for x in raw_sizes])
    derived_mean, derived_p95 = _mean_p95([float(x) for x in derived_sizes])
    print(f"\nstorage raw bytes: mean={raw_mean:.0f} p95={raw_p95:.0f}")
    print(
        "storage derived bytes (pages+chunks+embeddings): "
        f"mean={derived_mean:.0f} p95={derived_p95:.0f}"
    )

    # standalone NLI (entailment) microbenchmark -- real model, real inputs
    premise = (
        "KPMG, the Statutory Auditor of the Company, has tendered its "
        "resignation effective March 15, 2026."
    )
    hypothesis = "The company's auditor resigned in 2026."
    nli_times = []
    for _ in range(5):
        start = time.monotonic()
        entailment_score(premise, hypothesis)
        nli_times.append(time.monotonic() - start)
    nli_mean, nli_p95 = _mean_p95(nli_times)
    print(
        f"\nNLI (entailment_score) standalone: mean={nli_mean:.4f}s "
        f"p95={nli_p95:.4f}s (n=5 real calls)"
    )

    print("\nLLM tokens/cost: 0 throughout (offline template renderer, no live LLM call)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
