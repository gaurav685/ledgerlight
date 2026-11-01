"""Application configuration, loaded from environment variables / .env.

Phase 0 scope: only what the acquisition utility, manifest tooling and infra
checks actually use. Settings fail fast with actionable messages if required
values are missing or invalid.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEDGERLIGHT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Identifies this project to third-party servers (User-Agent contact
    # address) and is required before the acquisition utility will run.
    contact_email: str = Field(..., description="Contact email sent in the acquisition User-Agent")

    data_dir: Path = Field(
        default=Path("data"), description="Root directory for raw/interim/processed/manifests"
    )

    fetch_rate_limit_seconds: float = Field(
        default=2.0, ge=0.0, description="Minimum delay between requests to the same host"
    )
    fetch_timeout_seconds: float = Field(
        default=30.0, gt=0.0, description="Per-request HTTP timeout"
    )
    fetch_max_retries: int = Field(
        default=5, ge=0, description="Max retry attempts on 429/5xx responses"
    )
    fetch_max_file_size_bytes: int = Field(
        default=200_000_000, gt=0, description="Reject any single download above this size"
    )

    # Local infra (Docker Compose) — Phase 0 only proves these start healthy.
    postgres_host: str = Field(default="127.0.0.1")
    postgres_port: int = Field(default=55432, gt=0, le=65535)
    postgres_user: str = Field(default="ledgerlight")
    postgres_password: str = Field(default="changeme-local-only")
    postgres_db: str = Field(default="ledgerlight")

    # Generic S3-compatible endpoint for local infra (Garage; see
    # docs/adr/0003-object-storage.md). The ephemeral infra-check round-trip
    # (scripts/infra_check.py) still provisions its own throwaway key per
    # run. Phase 1's persistent raw-object bucket uses a stable key instead,
    # provisioned once by scripts/garage_provision.py into these settings.
    s3_endpoint: str = Field(default="127.0.0.1:59000")
    s3_region: str = Field(default="garage")
    s3_bucket: str = Field(default="ledgerlight-raw")
    s3_access_key_id: str | None = Field(default=None)
    s3_secret_access_key: str | None = Field(default=None)

    # Phase 1 metadata store (SQLAlchemy/Alembic) reuses postgres_db above
    # as the application database. Dagster gets its own database name, per
    # the Phase 1 brief — its run/event storage is never mixed with the
    # application schema.
    postgres_dagster_db: str = Field(default="ledgerlight_dagster")

    # Phase 5 §2: the API's own runtime DB role — a real, separate,
    # non-superuser role with no BYPASSRLS, distinct from `postgres_user`
    # above (the owner role migrations run under). RLS policies apply to
    # this role automatically because it neither owns the tables nor is a
    # superuser — never because FORCE ROW LEVEL SECURITY was set.
    app_db_user: str = Field(default="ledgerlight_app")
    app_db_password: str = Field(default="changeme-local-only-app")

    # Phase 5 §2: session cookie/CSRF token signing and webhook-secret
    # encryption-at-rest keys. Dev defaults are deliberately obviously-fake
    # (never a real secret) so §5's fail-fast weak-secret check has
    # something real to catch outside dev mode.
    session_secret_key: str = Field(default="dev-only-session-secret-change-me")
    # A real, valid Fernet key -- but a dev-only one, committed in plain sight
    # (never a real production secret) precisely so §5's fail-fast weak-secret
    # check has a known, matchable value to reject outside dev mode.
    webhook_secret_encryption_key: str = Field(
        default="UWhA93WPMUQ7e0aYCYjBP_nKSse4xZ0Bf6qC1TxZDyw="
    )

    # Phase 5 §3: the real session cookie's own Secure attribute -- False
    # by default (this environment serves plain http on localhost); set
    # True in any real deployment served over TLS.
    cookie_secure: bool = Field(default=False)

    def app_database_url(self, db_name: str | None = None) -> str:
        """The same database as `database_url()`, but authenticating as
        the restricted `app_db_user` role -- what the real API process
        connects as, never the owner role migrations use."""
        name = db_name or self.postgres_db
        return (
            f"postgresql+psycopg://{self.app_db_user}:{self.app_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{name}"
        )

    def database_url(self, db_name: str | None = None) -> str:
        name = db_name or self.postgres_db
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{name}"
        )

    @field_validator("contact_email")
    @classmethod
    def _contact_email_must_look_like_email(cls, v: str) -> str:
        if "@" not in v or v.strip() == "":
            raise ValueError(
                "LEDGERLIGHT_CONTACT_EMAIL must be a real contact address "
                "(sent in the acquisition User-Agent so hosts can reach us) — "
                f"got {v!r}"
            )
        return v


def load_settings() -> Settings:
    """Load settings, raising a clear error if required values are missing."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001 - re-raised with actionable context
        raise RuntimeError(
            "Failed to load Ledgerlight settings. Check your .env against "
            ".env.example — every required LEDGERLIGHT_* variable must be set.\n"
            f"Underlying error: {exc}"
        ) from exc
