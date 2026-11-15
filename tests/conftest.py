from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Prevent a developer's real .env (and real cwd) from leaking into unit tests.

    Settings.model_config points at a relative ".env" path, which pydantic-settings
    resolves against the process cwd — so without this, running tests from a repo
    checkout with a real local .env would make settings tests see real values.
    """
    for key in list(os.environ):
        if key.startswith("LEDGERLIGHT_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LEDGERLIGHT_CONTACT_EMAIL", "test@example.com")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A real Postgres session (the local Docker stack's app database),
    wrapped in a transaction that's rolled back at teardown so integration
    tests never leave rows behind. Skips cleanly if the stack isn't up —
    `make test-integration` / `docker compose up` is what's expected to
    provide it, not pytest itself."""
    repo_root = Path(__file__).resolve().parent.parent

    from ledgerlight.config.settings import Settings

    try:
        settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")

    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError

    engine = create_engine(settings.database_url())
    try:
        connection = engine.connect()
    except OperationalError as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def object_store():  # type: ignore[no-untyped-def]
    """A real S3-compatible object store (the local Garage stack). Skips
    cleanly if S3 credentials aren't configured -- same real convention
    as `db_session` above for Postgres. Found missing (these tests
    raised a hard RuntimeError instead) while re-verifying for the
    v0.9.0-preview push's first real CI run."""
    repo_root = Path(__file__).resolve().parent.parent

    from ledgerlight.config.settings import Settings
    from ledgerlight.storage.s3_store import ObjectStore

    settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    try:
        return ObjectStore(settings)
    except RuntimeError as exc:
        pytest.skip(f"S3/Garage not configured (is the Docker stack provisioned?): {exc}")
