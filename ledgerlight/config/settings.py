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
    # docs/adr/0003-object-storage.md). Credentials are provisioned
    # dynamically per infra-check run (scripts/infra_check.py), not read
    # from settings, because Garage issues keys via its admin CLI rather
    # than accepting a static root user/password like MinIO did.
    s3_endpoint: str = Field(default="127.0.0.1:59000")
    s3_region: str = Field(default="garage")

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
