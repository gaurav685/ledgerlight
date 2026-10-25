"""Create the ledgerlight_dagster database if it doesn't exist yet.

Dagster's Postgres storage classes create their own tables on first use,
but they don't create the database itself — that's on us, same as the
app database (see ledgerlight.db.session.ensure_database_exists).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ledgerlight.config.settings import load_settings  # noqa: E402
from ledgerlight.db.session import ensure_database_exists  # noqa: E402


def main() -> int:
    settings = load_settings()
    ensure_database_exists(settings, settings.postgres_dagster_db)
    print(f"OK: database {settings.postgres_dagster_db!r} exists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
