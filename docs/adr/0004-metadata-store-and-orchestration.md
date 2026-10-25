# ADR 0004: Metadata Store and Orchestration (Phase 1)

## Status
Accepted (Phase 1).

## Context
Phase 1 needs (a) a relational metadata store for documents, versions,
pages, price bars and provenance, and (b) an orchestrator for scheduled
and ad-hoc ingestion/processing jobs with retries, partitions and a
sensor for manual-inbox files. The brief specified SQLAlchemy 2.x +
Alembic + psycopg3 for the former and Dagster for the latter, run inside
the monolith (no Kafka/Kubernetes/Celery/extra queues).

## Decision

### Metadata store
SQLAlchemy 2.x declarative models (`ledgerlight/db/models.py`) + Alembic
migrations, against the same Postgres instance Phase 0 already stood up
(`infra/docker-compose.yml`), using the `psycopg` (v3) driver via
`postgresql+psycopg://`. Every timestamp column is `timestamptz` (UTC);
IST-stated source dates are converted once, explicitly, at the point of
parsing (`ledgerlight.common.timeutil.ist_date_to_utc`) — see
`docs/data/temporal-semantics.md`.

### Orchestration
Dagster (`dagster` + `dagster-postgres` + `dagster-webserver`), as a
package (`ledgerlight/orchestration/`) inside the same monolith — assets,
ops, jobs, a daily partition definition for bhavcopy, an inbox sensor and
a daily schedule, all in `ledgerlight/orchestration/definitions.py`.

Dagster's own run/event-log/schedule storage lives in Postgres **in a
separate database** (`ledgerlight_dagster`, `Settings.postgres_dagster_db`)
from the application schema (`ledgerlight_dagster.dagster.yaml`) — never
mixed with `documents`/`price_bars`/etc. The database is created on
demand by `scripts/dagster_db_setup.py` (mirroring
`ledgerlight.db.session.ensure_database_exists` for the app DB); Dagster's
own storage classes create their tables on first use.

## Two real compatibility bugs found and fixed while wiring this up

Both were only found by actually running the code against the real
Docker stack, not by reading the Dagster docs.

### 1. `context` type annotations must not be written via the `dg.` import alias under `from __future__ import annotations`

Dagster's `OpDefinition.__init__` validates the `context` parameter's
annotation with an **identity check** against its own imported
`AssetExecutionContext`/`OpExecutionContext`/`AssetCheckExecutionContext`
classes (`dagster/_core/definitions/op_definition.py::_validate_context_type_hint`),
using the raw, unresolved `inspect.signature(fn).parameters[0].annotation`
— not `typing.get_type_hints()`. With `from __future__ import annotations`
active (PEP 563), **every** annotation in the module becomes a lazy string
at runtime, so `context: dg.AssetExecutionContext` is literally the string
`"dg.AssetExecutionContext"` when Dagster inspects it — never equal to the
actual class object, regardless of which name or alias was used to import
it. The fix was to drop `from __future__ import annotations` from
`ledgerlight/orchestration/definitions.py` specifically (every other
annotation in that file — `dt.date`, `list[dict[str, Any]]`,
`dg.SkipReason | dg.RunRequest` — is fine without it on Python 3.12) and
import the four context classes directly (`from dagster import
AssetExecutionContext, OpExecutionContext, ScheduleEvaluationContext,
SensorEvaluationContext`) so the bare names resolve to real objects at
decoration time.

### 2. `dagster-postgres`'s `NOTIFY` call breaks under SQLAlchemy's psycopg3 dialect

`PostgresEventLogStorage.store_event` runs
`NOTIFY run_events, :notify_id;` as a parameterized statement on every
event. PostgreSQL's `NOTIFY` only accepts a **literal** payload string —
it has no grammar for a bound parameter there. psycopg2 (what
`dagster-postgres` was written and is normally tested against) hides this
because its default cursor does client-side `%s`-style string
interpolation before the query ever reaches the server. SQLAlchemy 2.x,
however, now resolves a bare `postgresql://` scheme to the `psycopg` (v3)
dialect by default when both drivers are installed (confirmed directly:
`sqlalchemy.create_engine("postgresql://...").dialect.driver ==
"psycopg"`), and psycopg3 always binds parameters server-side via the
extended query protocol — which fails with `psycopg.errors.SyntaxError:
syntax error at or near "$1"` for exactly this statement. Fixed without
touching `dagster-postgres` itself: `dagster_home/dagster.yaml` sets
`scheme: postgresql+psycopg2` on each of the three `postgres_db` storage
blocks, forcing Dagster's internal engine onto psycopg2 (already present
as a transitive dependency) while the **application**'s own engine
(`ledgerlight/db/session.py`) keeps using `postgresql+psycopg://` (v3)
unaffected — the two engines are entirely separate and never share a
connection pool.

## Consequences
- Dagster's Postgres storage and the application's metadata store are
  two physically separate databases on the same Postgres server, so a
  `DROP DATABASE ledgerlight_dagster` (e.g. to reset orchestration state)
  can never touch application data and vice versa.
- Dagster's internal connections use psycopg2; everything else in the
  codebase uses psycopg3. This is isolated entirely to
  `dagster_home/dagster.yaml`'s `scheme:` keys — no application code
  depends on which driver Dagster uses internally.
- `ledgerlight/orchestration/definitions.py` cannot use
  `from __future__ import annotations`, unlike the rest of the codebase.
  This is called out in that file's own module docstring so it isn't
  "fixed" again by accident in a future refactor.
