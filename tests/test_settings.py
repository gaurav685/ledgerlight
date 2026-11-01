from __future__ import annotations

import pytest

from ledgerlight.config.settings import load_settings


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGERLIGHT_CONTACT_EMAIL", "someone@example.com")
    settings = load_settings()
    assert settings.contact_email == "someone@example.com"
    assert settings.fetch_rate_limit_seconds == 2.0


def test_settings_missing_contact_email_fails_actionably(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEDGERLIGHT_CONTACT_EMAIL", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        load_settings()
    assert "contact_email" in str(excinfo.value).lower()
    assert ".env.example" in str(excinfo.value)


def test_settings_invalid_contact_email_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGERLIGHT_CONTACT_EMAIL", "not-an-email")
    with pytest.raises(RuntimeError):
        load_settings()


def test_settings_rate_limit_rejects_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGERLIGHT_CONTACT_EMAIL", "someone@example.com")
    monkeypatch.setenv("LEDGERLIGHT_FETCH_RATE_LIMIT_SECONDS", "-1")
    with pytest.raises(RuntimeError):
        load_settings()


def test_settings_dev_environment_allows_every_weak_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEDGERLIGHT_CONTACT_EMAIL", "someone@example.com")
    settings = load_settings()
    assert settings.environment == "dev"
    assert settings.cookie_secure is False  # a real weak default, but dev is exempt


def test_settings_production_rejects_every_real_weak_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEDGERLIGHT_CONTACT_EMAIL", "someone@example.com")
    monkeypatch.setenv("LEDGERLIGHT_ENVIRONMENT", "production")
    with pytest.raises(RuntimeError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert "LEDGERLIGHT_POSTGRES_PASSWORD" in message
    assert "LEDGERLIGHT_APP_DB_PASSWORD" in message
    assert "LEDGERLIGHT_SESSION_SECRET_KEY" in message
    assert "LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY" in message
    assert "LEDGERLIGHT_COOKIE_SECURE" in message


def test_settings_production_with_every_real_value_changed_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEDGERLIGHT_CONTACT_EMAIL", "someone@example.com")
    monkeypatch.setenv("LEDGERLIGHT_ENVIRONMENT", "production")
    monkeypatch.setenv("LEDGERLIGHT_POSTGRES_PASSWORD", "a-real-distinct-password")
    monkeypatch.setenv("LEDGERLIGHT_APP_DB_PASSWORD", "another-real-distinct-password")
    monkeypatch.setenv("LEDGERLIGHT_SESSION_SECRET_KEY", "a-real-distinct-session-secret")
    monkeypatch.setenv(
        "LEDGERLIGHT_WEBHOOK_SECRET_ENCRYPTION_KEY", "a-real-distinct-fernet-key-value"
    )
    monkeypatch.setenv("LEDGERLIGHT_COOKIE_SECURE", "true")
    settings = load_settings()
    assert settings.environment == "production"
