"""Dagster assets, jobs, schedules, partitions and the inbox sensor.

Dagster's own run/event storage lives in a separate database
(settings.postgres_dagster_db) — never the application schema. See
docs/adr/0004-metadata-store-and-orchestration.md.

Deliberately NOT using `from __future__ import annotations` here, unlike
most of the codebase: Dagster validates `context` parameter annotations
by identity against its own imported context classes using the raw,
unresolved annotation, so a lazy-string annotation (what PEP 563 produces)
never matches — see ADR 0004 for the exact failure and why every context
parameter below imports its class directly rather than via the `dg.`
alias.
"""

import datetime as dt

import dagster as dg
from dagster import (
    AssetExecutionContext,
    OpExecutionContext,
    ScheduleEvaluationContext,
    SensorEvaluationContext,
)

from ledgerlight.acquisition.import_local import import_inbox
from ledgerlight.config.settings import load_settings
from ledgerlight.db.session import make_session_factory
from ledgerlight.ingestion.care import run_care_discovery_job
from ledgerlight.ingestion.ibbi import run_ibbi_discovery_job
from ledgerlight.ingestion.known_items import run_known_items_job
from ledgerlight.ingestion.nse_bhavcopy import run_bhavcopy_range
from ledgerlight.ingestion.sebi import run_sebi_discovery_job
from ledgerlight.storage.s3_store import ObjectStore

# Partitions start where the Correction-1 seed's own coverage starts.
# Phase 1's backfill extension (§4 of the brief) goes further back than
# this for the one-time historical load; the day-to-day *partition*
# definition covers the ongoing window.
BHAVCOPY_PARTITIONS = dg.DailyPartitionsDefinition(start_date="2017-01-01")

_RETRY_POLICY = dg.RetryPolicy(max_retries=2, delay=5)

_KNOWN_ITEM_SOURCES = (
    "sebi",
    "ibbi",
    "care",
    "vakrangee_ir",
    "jetairways_ir",
    "brightcom_ir",
    "lichousing_ir",
    "pnbhousing_ir",
    "spicejet_ir",
    "dmart_ir",
    # thermax_ir removed 2026-11-06 (Phase 6A §11): its robots.txt now
    # explicitly disallows ClaudeBot by name. Same precedent already
    # applied to "crisil" above -- see data/manifests/sources.yaml's
    # retest_2026_11_06.thermax_ir entry.
    "suzlon_ir",
    "mastek_ir",
)


@dg.asset(partitions_def=BHAVCOPY_PARTITIONS, retry_policy=_RETRY_POLICY)
def bhavcopy_daily(context: AssetExecutionContext) -> dg.MaterializeResult:
    """One partition = one calendar day's NSE equity bhavcopy."""
    partition_date = dt.date.fromisoformat(context.partition_key)
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    from ledgerlight.acquisition.fetcher import PoliteFetcher

    with (
        session_factory() as session,
        PoliteFetcher(
            contact_email=settings.contact_email,
            data_dir=settings.data_dir,
            manifest_path=settings.data_dir / "manifests" / "live_ingestion.jsonl",
            rate_limit_seconds=settings.fetch_rate_limit_seconds,
            timeout_seconds=settings.fetch_timeout_seconds,
            max_retries=settings.fetch_max_retries,
            max_file_size_bytes=settings.fetch_max_file_size_bytes,
        ) as fetcher,
    ):
        stats = run_bhavcopy_range(session, store, fetcher, partition_date, partition_date)

    context.log.info(f"bhavcopy {partition_date}: {stats}")
    return dg.MaterializeResult(
        metadata={
            "fetched_new": stats.fetched_new,
            "unchanged": stats.unchanged,
            "not_found": stats.not_found,
            "errors": len(stats.errors),
        }
    )


def _make_known_items_op(source_id: str) -> dg.OpDefinition:
    @dg.op(name=f"ingest_{source_id}", retry_policy=_RETRY_POLICY)
    def _op(context: OpExecutionContext) -> None:
        settings = load_settings()
        store = ObjectStore(settings)
        session_factory = make_session_factory(settings)

        from ledgerlight.acquisition.fetcher import PoliteFetcher

        with (
            session_factory() as session,
            PoliteFetcher(
                contact_email=settings.contact_email,
                data_dir=settings.data_dir,
                manifest_path=settings.data_dir / "manifests" / "live_ingestion.jsonl",
                rate_limit_seconds=settings.fetch_rate_limit_seconds,
                timeout_seconds=settings.fetch_timeout_seconds,
                max_retries=settings.fetch_max_retries,
                max_file_size_bytes=settings.fetch_max_file_size_bytes,
            ) as fetcher,
        ):
            stats = run_known_items_job(session, store, fetcher, source_id)
        context.log.info(f"{source_id}: {stats}")

    return _op


_known_items_ops = {source_id: _make_known_items_op(source_id) for source_id in _KNOWN_ITEM_SOURCES}


def _make_known_items_job(source_id: str) -> dg.JobDefinition:
    op = _known_items_ops[source_id]

    @dg.job(name=f"{source_id}_job")
    def _job() -> None:
        op()

    return _job


known_items_jobs = {
    source_id: _make_known_items_job(source_id) for source_id in _KNOWN_ITEM_SOURCES
}


@dg.op(name="care_discovery", retry_policy=_RETRY_POLICY)
def care_discovery_op(context: OpExecutionContext) -> None:
    """Phase 3 Sec2.2: per-SEED-company CARE rationale discovery (beyond the
    single hardcoded DHFL known_items entry) -- see ledgerlight.ingestion
    .care for the real discovery mechanism this drives."""
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    from ledgerlight.acquisition.fetcher import PoliteFetcher

    with (
        session_factory() as session,
        PoliteFetcher(
            contact_email=settings.contact_email,
            data_dir=settings.data_dir,
            manifest_path=settings.data_dir / "manifests" / "live_ingestion.jsonl",
            rate_limit_seconds=settings.fetch_rate_limit_seconds,
            timeout_seconds=settings.fetch_timeout_seconds,
            max_retries=settings.fetch_max_retries,
            max_file_size_bytes=settings.fetch_max_file_size_bytes,
        ) as fetcher,
    ):
        stats = run_care_discovery_job(session, store, fetcher, settings.contact_email)
    context.log.info(f"care_discovery: {stats}")


@dg.job(name="care_discovery_job")
def care_discovery_job() -> None:
    care_discovery_op()


@dg.op(name="ibbi_discovery", retry_policy=_RETRY_POLICY)
def ibbi_discovery_op(context: OpExecutionContext) -> None:
    """Phase 3 Sec2.3: per-SEED-company IBBI NCLT order discovery (beyond
    the four hand-found known_items entries) -- see ledgerlight.ingestion
    .ibbi for the real discovery mechanism this drives."""
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    from ledgerlight.acquisition.fetcher import PoliteFetcher

    with (
        session_factory() as session,
        PoliteFetcher(
            contact_email=settings.contact_email,
            data_dir=settings.data_dir,
            manifest_path=settings.data_dir / "manifests" / "live_ingestion.jsonl",
            rate_limit_seconds=settings.fetch_rate_limit_seconds,
            timeout_seconds=settings.fetch_timeout_seconds,
            max_retries=settings.fetch_max_retries,
            max_file_size_bytes=settings.fetch_max_file_size_bytes,
        ) as fetcher,
    ):
        stats = run_ibbi_discovery_job(session, store, fetcher, settings.contact_email)
    context.log.info(f"ibbi_discovery: {stats}")


@dg.job(name="ibbi_discovery_job")
def ibbi_discovery_job() -> None:
    ibbi_discovery_op()


@dg.op(name="sebi_discovery", retry_policy=_RETRY_POLICY)
def sebi_discovery_op(context: OpExecutionContext) -> None:
    """Phase 3 Sec2.3: per-SEED-company SEBI enforcement-order discovery
    (beyond the hand-found known_items entries) -- see ledgerlight
    .ingestion.sebi for the real discovery mechanism this drives."""
    settings = load_settings()
    store = ObjectStore(settings)
    session_factory = make_session_factory(settings)

    from ledgerlight.acquisition.fetcher import PoliteFetcher

    with (
        session_factory() as session,
        PoliteFetcher(
            contact_email=settings.contact_email,
            data_dir=settings.data_dir,
            manifest_path=settings.data_dir / "manifests" / "live_ingestion.jsonl",
            rate_limit_seconds=settings.fetch_rate_limit_seconds,
            timeout_seconds=settings.fetch_timeout_seconds,
            max_retries=settings.fetch_max_retries,
            max_file_size_bytes=settings.fetch_max_file_size_bytes,
        ) as fetcher,
    ):
        stats = run_sebi_discovery_job(session, store, fetcher, settings.contact_email)
    context.log.info(f"sebi_discovery: {stats}")


@dg.job(name="sebi_discovery_job")
def sebi_discovery_job() -> None:
    sebi_discovery_op()


bhavcopy_job = dg.define_asset_job(name="bhavcopy_job", selection=[bhavcopy_daily])


@dg.op
def import_inbox_op(context: OpExecutionContext) -> None:
    settings = load_settings()
    result = import_inbox(data_dir=settings.data_dir)
    context.log.info(
        f"inbox: imported={len(result.imported)} skipped={len(result.skipped_duplicate)} "
        f"rejected={len(result.rejected_no_provenance)}"
    )


@dg.job
def inbox_import_job() -> None:
    import_inbox_op()


@dg.sensor(job=inbox_import_job, minimum_interval_seconds=30)
def inbox_sensor(context: SensorEvaluationContext) -> dg.SkipReason | dg.RunRequest:
    settings = load_settings()
    inbox_dir = settings.data_dir / "inbox"
    if not inbox_dir.exists():
        return dg.SkipReason("data/inbox/ does not exist")
    files = [p for p in inbox_dir.iterdir() if p.is_file() and p.name != "provenance.csv"]
    if not files:
        return dg.SkipReason("no files in data/inbox/")
    cursor_key = ",".join(sorted(p.name for p in files))
    if context.cursor == cursor_key:
        return dg.SkipReason("same inbox contents as last evaluation")
    context.update_cursor(cursor_key)
    return dg.RunRequest(run_key=cursor_key)


@dg.schedule(cron_schedule="30 18 * * 1-5", job=bhavcopy_job)
def bhavcopy_daily_schedule(context: ScheduleEvaluationContext) -> dg.RunRequest:
    """18:30 IST, Mon-Fri — NSE publishes same-day bhavcopy a few hours
    after market close. Targets "today" (IST) as the partition."""
    ist_now = context.scheduled_execution_time.astimezone(
        dt.timezone(dt.timedelta(hours=5, minutes=30))
    )
    partition_key = ist_now.date().isoformat()
    return dg.RunRequest(partition_key=partition_key)


# --- Phase 2 knowledge pipeline: chunk -> embed -> extract -> resolve
# entities. Each op wraps the same idempotent function the standalone
# scripts/*.py CLIs call directly -- one implementation, two ways to run
# it (ad-hoc via the script, or orchestrated here with retries/run IDs).
_KNOWLEDGE_RETRY_POLICY = dg.RetryPolicy(max_retries=2, delay=5)


@dg.op(retry_policy=_KNOWLEDGE_RETRY_POLICY)
def chunk_corpus_op(context: OpExecutionContext) -> None:
    from sqlalchemy import select

    from ledgerlight.db.models import DocumentVersion
    from ledgerlight.knowledge.chunking import chunk_version

    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        versions = session.scalars(
            select(DocumentVersion).where(
                DocumentVersion.mime_type.in_(["application/pdf", "text/html"])
            )
        ).all()
        chunks_created = sum(chunk_version(session, v).chunks_created for v in versions)
    context.log.info(f"chunk_corpus: versions={len(versions)} chunks_created={chunks_created}")


@dg.op(retry_policy=_KNOWLEDGE_RETRY_POLICY, ins={"after": dg.In(dg.Nothing)})
def embed_chunks_op(context: OpExecutionContext) -> None:
    from sqlalchemy import select

    from ledgerlight.knowledge.embedding import (
        EMBEDDING_MODEL_NAME,
        EMBEDDING_MODEL_VERSION,
        embed_texts,
    )
    from ledgerlight.knowledge.models import Chunk

    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        chunks = session.scalars(select(Chunk).where(Chunk.embedding.is_(None))).all()
        for i in range(0, len(chunks), 32):
            batch = chunks[i : i + 32]
            vectors = embed_texts([c.text for c in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model_name = EMBEDDING_MODEL_NAME
                chunk.embedding_model_version = EMBEDDING_MODEL_VERSION
            session.commit()
    context.log.info(f"embed_chunks: embedded={len(chunks)}")


@dg.op(retry_policy=_KNOWLEDGE_RETRY_POLICY, ins={"after": dg.In(dg.Nothing)})
def extract_aud_resign_op(context: OpExecutionContext) -> None:
    from sqlalchemy import select

    from ledgerlight.knowledge.classifier import rules_baseline_predict
    from ledgerlight.knowledge.extraction_pipeline import run_aud_resign_extraction
    from ledgerlight.knowledge.models import Chunk

    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        chunks = session.scalars(select(Chunk).order_by(Chunk.id)).all()
        candidate_ids = [c.id for c in chunks if rules_baseline_predict(c.text) == "AUD_RESIGN"]
        stats = run_aud_resign_extraction(session, candidate_ids)
    context.log.info(
        f"extract: events_created={stats.events_created} fields_created={stats.fields_created}"
    )


@dg.op(retry_policy=_KNOWLEDGE_RETRY_POLICY, ins={"after": dg.In(dg.Nothing)})
def resolve_entities_op(context: OpExecutionContext) -> None:
    from ledgerlight.knowledge.entity_bootstrap import (
        bootstrap_audit_firm_entities,
        bootstrap_company_entities,
    )

    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        company_stats = bootstrap_company_entities(session)
        audit_stats = bootstrap_audit_firm_entities(session)
    context.log.info(
        f"resolve_entities: companies={company_stats.company_entities_created} "
        f"audit_links={audit_stats.audit_firm_links_created}"
    )


@dg.job
def knowledge_pipeline_job() -> None:
    chunked = chunk_corpus_op()
    embedded = embed_chunks_op(after=chunked)
    extracted = extract_aud_resign_op(after=embedded)
    resolve_entities_op(after=extracted)


@dg.op(name="event_study_run", retry_policy=_RETRY_POLICY)
def event_study_run_op(context: OpExecutionContext) -> None:
    """Enhancement 1: runs the real, pre-registered governance event
    study against the frozen `spec.v1.json` (the spec-hash freeze
    guard refuses to run under an edited, un-frozen spec). Deliberately
    NOT on any schedule -- this op is wired only into
    `event_study_job` below, which nothing triggers automatically; a
    human runs it by hand, per the brief's own "run manually only"
    requirement."""
    from pathlib import Path

    from ledgerlight.research.event_study import (
        current_git_sha,
        load_and_verify_spec,
        run_event_study,
    )

    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "docs" / "enhancements" / "event-study" / "spec.v1.json"
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        spec = load_and_verify_spec(session, spec_path, "v1")
        git_sha = current_git_sha(repo_root)
        result = run_event_study(session, spec, git_sha, "dagster:event_study_run_op")
    context.log.info(f"event_study_run: run_id={result.run_id}")


@dg.op(name="event_study_report", retry_policy=_RETRY_POLICY, ins={"after": dg.In(dg.Nothing)})
def event_study_report_op(context: OpExecutionContext) -> None:
    """Enhancement 1: generates `docs/enhancements/event-study/report.md`
    and the real CAAR plots from the LATEST real `event_study_runs`
    row -- never a fresh recomputation."""
    from pathlib import Path

    from sqlalchemy import select

    from ledgerlight.research.models import EventStudyRun
    from ledgerlight.research.report import generate_report

    repo_root = Path(__file__).resolve().parents[2]
    settings = load_settings()
    session_factory = make_session_factory(settings)
    with session_factory() as session:
        latest_id = session.execute(
            select(EventStudyRun.id).order_by(EventStudyRun.created_at.desc()).limit(1)
        ).scalar_one()
        report_path = generate_report(session, latest_id, repo_root)
    context.log.info(f"event_study_report: {report_path}")


@dg.job(name="event_study_job")
def event_study_job() -> None:
    """Enhancement 1's own "run -> report" chain. Not on any schedule
    or sensor -- run manually, per the brief's own requirement."""
    ran = event_study_run_op()
    event_study_report_op(after=ran)


def _run_script_main(script_name: str) -> int:
    """Loads one scripts/*.py module's main() and calls it, the same
    dynamic-import technique this project's own tests already use
    (scripts/ is deliberately not a package -- see its CLI-first
    docstrings) -- so a Dagster op can drive the exact same idempotent
    build logic a human runs by hand, without a parallel reimplementation."""
    import importlib.util
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        script_name.replace("/", "_").removesuffix(".py"), repo_root / script_name
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


@dg.op(name="outcomes_build", retry_policy=_RETRY_POLICY)
def outcomes_build_op(context: OpExecutionContext) -> None:
    """Phase 3 §3/§9 asset stage "outcomes": populate real Outcome rows
    -- see scripts/populate_outcomes.py. Idempotent (skips already-
    existing (event_type, company, event_time) rows)."""
    exit_code = _run_script_main("scripts/populate_outcomes.py")
    context.log.info(f"outcomes_build: exit_code={exit_code}")


@dg.op(name="feature_snapshots_build", retry_policy=_RETRY_POLICY, ins={"after": dg.In(dg.Nothing)})
def feature_snapshots_build_op(context: OpExecutionContext) -> None:
    """Phase 3 §4/§9 asset stage "feature_snapshots": builds all three
    real feature tiers in sequence (STRUCTURED, then the two tiers that
    reuse its (company_id, as_of) grid). Each script upserts on
    conflict, so re-running is safe and idempotent per feature_set_version."""
    for script_name in (
        "scripts/build_feature_snapshots.py",
        "scripts/build_rule_verified_features.py",
        "scripts/build_seed_governance_features.py",
    ):
        exit_code = _run_script_main(script_name)
        context.log.info(f"feature_snapshots_build: {script_name} exit_code={exit_code}")


@dg.job(name="outcomes_and_features_build_job")
def outcomes_and_features_build_job() -> None:
    """The real "outcomes -> feature_snapshots" asset chain the brief's
    §9 asks for, as an op-based job (matching this file's existing
    convention for every other Phase 3 build step -- e.g. care/ibbi/sebi
    discovery -- rather than introducing `@dg.asset` only here)."""
    built = outcomes_build_op()
    feature_snapshots_build_op(after=built)


@dg.op(name="train_risk", retry_policy=_RETRY_POLICY)
def train_risk_op(context: OpExecutionContext) -> None:
    """Phase 3 §6/§9 asset stage "train" -- deliberately MANUAL (no
    schedule): trains one final LightGBM model on the full real
    labeled dataset and records it in model_registry -- see
    scripts/train_risk.py. Idempotent per model_name/model_version
    (deterministic seeds; a second run uploads nothing new to Garage)."""
    exit_code = _run_script_main("scripts/train_risk.py")
    context.log.info(f"train_risk: exit_code={exit_code}")


@dg.op(name="score", retry_policy=_RETRY_POLICY)
def score_op(context: OpExecutionContext) -> None:
    """Phase 3 §8/§9 asset stage "score": loads the trained artifact
    from Garage and writes real scores for the verified-coverage
    universe at each company's own latest real feature snapshot -- see
    scripts/score.py. Idempotent per (company_id, as_of, model_name,
    model_version) via the real ON CONFLICT upsert in
    ledgerlight.modelling.scoring.write_scores."""
    exit_code = _run_script_main("scripts/score.py")
    context.log.info(f"score: exit_code={exit_code}")


@dg.op(name="reports", retry_policy=_RETRY_POLICY, ins={"after": dg.In(dg.Nothing)})
def reports_op(context: OpExecutionContext) -> None:
    """Phase 3 §9/§11 asset stage "reports": regenerates
    docs/modelling/model-card.md directly from the real pipeline
    results -- see scripts/model_card.py."""
    exit_code = _run_script_main("scripts/model_card.py")
    context.log.info(f"reports: exit_code={exit_code}")


@dg.job(name="risk_train_job")
def risk_train_job() -> None:
    """The real "train" asset stage -- manual trigger only, per the
    brief's own §9 asset chain ("train (manual)"); never scheduled."""
    train_risk_op()


@dg.job(name="risk_score_and_report_job")
def risk_score_and_report_job() -> None:
    """The real "score -> reports" asset chain -- see
    risk_score_monthly_schedule for the brief's §9 "score (monthly
    schedule)" requirement."""
    scored = score_op()
    reports_op(after=scored)


@dg.schedule(cron_schedule="0 6 1 * *", job=risk_score_and_report_job)
def risk_score_monthly_schedule(context: ScheduleEvaluationContext) -> dg.RunRequest:
    """06:00 UTC on the 1st of each month -- the brief's §9 "score
    (monthly schedule)" requirement. Scores whatever real feature
    snapshots exist as of run time; never a future date."""
    run_key = context.scheduled_execution_time.date().isoformat()
    return dg.RunRequest(run_key=run_key)


@dg.op(name="alerts_generate", retry_policy=_RETRY_POLICY)
def alerts_generate_op(context: OpExecutionContext) -> None:
    """Phase 5 §3's own "alerts generation" job: evaluates every real,
    active `alert_rules` row against new real events/scores for its
    own watchlist's companies, creates real `alerts` rows, and
    triggers real webhook deliveries -- see scripts/generate_alerts.py.
    Idempotent per (alert_rule, fact), so re-running is always safe."""
    exit_code = _run_script_main("scripts/generate_alerts.py")
    context.log.info(f"alerts_generate: exit_code={exit_code}")


@dg.job(name="alerts_generate_job")
def alerts_generate_job() -> None:
    alerts_generate_op()


@dg.schedule(cron_schedule="*/15 * * * *", job=alerts_generate_job)
def alerts_generate_schedule(context: ScheduleEvaluationContext) -> dg.RunRequest:
    """Every 15 minutes -- real watchlist alerts should reach a tenant
    soon after a new event/score lands, not just once a month like the
    risk-scoring job."""
    run_key = context.scheduled_execution_time.isoformat()
    return dg.RunRequest(run_key=run_key)


defs = dg.Definitions(
    assets=[bhavcopy_daily],
    jobs=[
        bhavcopy_job,
        inbox_import_job,
        knowledge_pipeline_job,
        care_discovery_job,
        ibbi_discovery_job,
        sebi_discovery_job,
        outcomes_and_features_build_job,
        risk_train_job,
        risk_score_and_report_job,
        alerts_generate_job,
        event_study_job,
        *known_items_jobs.values(),
    ],
    schedules=[bhavcopy_daily_schedule, risk_score_monthly_schedule, alerts_generate_schedule],
    sensors=[inbox_sensor],
)
