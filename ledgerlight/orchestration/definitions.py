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
from ledgerlight.ingestion.known_items import run_known_items_job
from ledgerlight.ingestion.nse_bhavcopy import run_bhavcopy_range
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
    "thermax_ir",
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


defs = dg.Definitions(
    assets=[bhavcopy_daily],
    jobs=[bhavcopy_job, inbox_import_job, *known_items_jobs.values()],
    schedules=[bhavcopy_daily_schedule],
    sensors=[inbox_sensor],
)
