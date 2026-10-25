"""Engine/session factory and the create-database-if-missing helper.

Postgres' single POSTGRES_DB env var (infra/docker-compose.yml) only
creates one database at container init, but Phase 1 needs two (app +
Dagster's own storage, kept separate per the brief). The second database
is created here, idempotently, rather than via a Compose init script.
"""

from __future__ import annotations

import psycopg
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ledgerlight.config.settings import Settings


def ensure_database_exists(settings: Settings, db_name: str) -> None:
    """CREATE DATABASE db_name if it doesn't already exist. Idempotent."""
    dsn = (
        f"host={settings.postgres_host} port={settings.postgres_port} "
        f"dbname={settings.postgres_db} user={settings.postgres_user} "
        f"password={settings.postgres_password}"
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if exists is None:
            conn.execute(f'CREATE DATABASE "{db_name}"')


def make_engine(settings: Settings, db_name: str | None = None) -> Engine:
    return create_engine(settings.database_url(db_name), future=True)


def make_session_factory(settings: Settings, db_name: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(settings, db_name), expire_on_commit=False)
