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
