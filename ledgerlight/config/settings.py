"""Application configuration, loaded from environment variables / .env.

Phase 0 scope: only what the acquisition utility, manifest tooling and infra
checks actually use. Settings fail fast with actionable messages if required
values are missing or invalid.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Phase 5 §5: the real, known-weak default values every dev-only secret
# below uses -- committed in plain sight on purpose (never a real
# production secret) so the fail-fast check in `_no_weak_secrets_outside_dev`
# has exact values to match against, rather than a heuristic.
_DEV_DEFAULT_POSTGRES_PASSWORD = "changeme-local-only"
_DEV_DEFAULT_APP_DB_PASSWORD = "changeme-local-only-app"
_DEV_DEFAULT_SESSION_SECRET_KEY = "dev-only-session-secret-change-me"
_DEV_DEFAULT_WEBHOOK_KEY = "UWhA93WPMUQ7e0aYCYjBP_nKSse4xZ0Bf6qC1TxZDyw="  # gitleaks:allow


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEDGERLIGHT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Phase 5 §5: real environments this process can run as. "dev" is the
    # default (every weak-secret default below is intentionally safe to
    # use in dev) -- outside dev, `_no_weak_secrets_outside_dev` fails
    # fast if any of them are still in their dev-only default state.
    environment: Literal["dev", "staging", "production"] = Field(default="dev")

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
    postgres_password: str = Field(default=_DEV_DEFAULT_POSTGRES_PASSWORD)
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
    app_db_password: str = Field(default=_DEV_DEFAULT_APP_DB_PASSWORD)

    # Phase 5 §2: session cookie/CSRF token signing and webhook-secret
    # encryption-at-rest keys. Dev defaults are deliberately obviously-fake
    # (never a real secret) so §5's fail-fast weak-secret check has
    # something real to catch outside dev mode.
    session_secret_key: str = Field(default=_DEV_DEFAULT_SESSION_SECRET_KEY)
    # A real, valid Fernet key -- but a dev-only one, committed in plain sight
    # (never a real production secret) precisely so §5's fail-fast weak-secret
    # check has a known, matchable value to reject outside dev mode.
    webhook_secret_encryption_key: str = Field(default=_DEV_DEFAULT_WEBHOOK_KEY)

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

    @model_validator(mode="after")
    def _no_weak_secrets_outside_dev(self) -> Settings:
        """Phase 5 §5: fails fast at startup -- never silently -- if this
        process claims to be `staging`/`production` but is still carrying
        one or more of the real, committed dev-only default secrets. A
        real deployment config must set every one of these explicitly;
        `environment="dev"` (the default) is the only state these defaults
        are ever safe in."""
        if self.environment == "dev":
            return self
        weak: list[str] = []
        if self.postgres_password == _DEV_DEFAULT_POSTGRES_PASSWORD:
            weak.append("LEDGERLIGHT_POSTGRES_PASSWORD")
        if self.app_db_password == _DEV_DEFAULT_APP_DB_PASSWORD:
            weak.append("LEDGERLIGHT_APP_DB_PASSWORD")
        if self.session_secret_key == _DEV_DEFAULT_SESSION_SECRET_KEY:
            weak.append("LEDGERLIGHT_SESSION_SECRET_KEY")
        if self.webhook_secret_encryption_key == _DEV_DEFAULT_WEBHOOK_KEY:
            weak.append("LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY")
        if not self.cookie_secure:
            weak.append("LEDGERLIGHT_COOKIE_SECURE (must be true outside dev)")
        if weak:
            raise ValueError(
                f"LEDGERLIGHT_ENVIRONMENT={self.environment!r} but the following "
                f"settings are still at their real dev-only default: {', '.join(weak)}. "
                "Set every one of these to a real, distinct value before running "
                "outside dev -- see .env.example."
            )
        return self


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
