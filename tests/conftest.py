from __future__ import annotations

import os
from pathlib import Path

import pytest


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
