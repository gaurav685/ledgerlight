"""Phase 5 §3: real end-to-end tests for the signed-document-link
endpoint. Presigned URL generation is pure local signing (no real
network call), so this exercises the real boto3/Garage client
end to end against the real local S3-compatible stack."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from ledgerlight.api import auth
from ledgerlight.api.models import Membership, Tenant, User
from ledgerlight.config.settings import Settings
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.db.session import make_session_factory

pytestmark = pytest.mark.integration


@pytest.fixture
def real_session() -> Iterator[Session]:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    try:
        settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")
    try:
        session = make_session_factory(settings)()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    created: dict[str, list[uuid.UUID]] = {"tenants": [], "documents": []}
    session.info["created"] = created
    try:
        yield session
    finally:
        session.execute(text("DELETE FROM rate_limit_counters WHERE key LIKE 'login_ip:%'"))
        if created["documents"]:
            session.execute(
                text(
                    "DELETE FROM document_pages WHERE version_id IN "
                    "(SELECT id FROM document_versions WHERE document_id = ANY(:ids))"
                ),
                {"ids": created["documents"]},
            )
            session.execute(
                text("DELETE FROM document_versions WHERE document_id = ANY(:ids)"),
                {"ids": created["documents"]},
            )
            session.execute(
                text("DELETE FROM documents WHERE id = ANY(:ids)"), {"ids": created["documents"]}
            )
        if created["tenants"]:
            session.execute(
                text("DELETE FROM audit_logs WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM sessions WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM memberships WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM users WHERE tenant_id = ANY(:ids)"), {"ids": created["tenants"]}
            )
            session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": created["tenants"]}
            )
        session.commit()
        session.close()


def _login(client: TestClient, real_session: Session, role: str) -> Tenant:
    tenant = Tenant(name="Documents Test Co", slug=f"documents-test-{uuid.uuid4().hex[:8]}")
    real_session.add(tenant)
    real_session.flush()
    real_session.info["created"]["tenants"].append(tenant.id)
    user = User(
        tenant_id=tenant.id,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=auth.hash_password("CorrectHorseBatteryStaple"),
    )
    real_session.add(user)
    real_session.flush()
    real_session.add(Membership(tenant_id=tenant.id, user_id=user.id, role=role, status="active"))
    real_session.commit()

    response = client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
    )
    if response.status_code == 503:
        pytest.skip("ledgerlight_app role not reachable")
    assert response.status_code == 200, response.text
    return tenant


def _make_document_version(real_session: Session) -> DocumentVersion:
    document = Document(
        source_id="sebi",
        source_key=f"test://api-documents/{uuid.uuid4()}",
        document_type="announcement",
    )
    real_session.add(document)
    real_session.flush()
    real_session.info["created"]["documents"].append(document.id)

    now = dt.datetime.now(dt.UTC)
    version = DocumentVersion(
        document_id=document.id,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        object_key=f"raw/test/{uuid.uuid4()}.pdf",
        bytes=100,
        mime_type="application/pdf",
        retrieval_method="automated_fetch",
        retrieval_url="https://example.com/test.pdf",
        retrieved_at=now,
        known_at=now,
        known_at_basis="retrieved_at",
        tool_version="test/1",
    )
    real_session.add(version)
    real_session.commit()
    return version


def _make_document_page(real_session: Session, version: DocumentVersion, raw_text: str) -> None:
    import hashlib

    real_session.add(
        DocumentPage(
            version_id=version.id,
            page_number=1,
            raw_text=raw_text,
            text_sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            char_count=len(raw_text),
            extraction_method="text_layer",
            extractor_version="test/1",
        )
    )
    real_session.commit()


@pytest.fixture
def client() -> TestClient:
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def _restore_real_s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`tests/conftest.py`'s own `_isolate_env` (autouse) wipes every
    real `LEDGERLIGHT_*` env var so `Settings()` never accidentally
    sees real values -- most settings this project uses have a
    class-level default that happens to equal the real local dev
    value (so `load_settings()` keeps working regardless), but
    `s3_access_key_id`/`s3_secret_access_key` correctly have no such
    default (they're real generated secrets, not safe to hardcode).
    The real router endpoint under test calls `load_settings()`
    internally with no override, so this test needs these two real
    values put back for its own duration -- `monkeypatch.setenv`
    reverts them automatically at teardown, same as `_isolate_env`
    itself."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    if not settings.s3_access_key_id or not settings.s3_secret_access_key:
        pytest.skip("no real S3/Garage credentials configured in .env")
    monkeypatch.setenv("LEDGERLIGHT_S3_ACCESS_KEY_ID", settings.s3_access_key_id)
    monkeypatch.setenv("LEDGERLIGHT_S3_SECRET_ACCESS_KEY", settings.s3_secret_access_key)
    monkeypatch.setenv("LEDGERLIGHT_S3_ENDPOINT", settings.s3_endpoint)
    monkeypatch.setenv("LEDGERLIGHT_S3_BUCKET", settings.s3_bucket)


def test_signed_url_for_a_real_document_version_is_capped_at_300_seconds(
    client: TestClient, real_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _restore_real_s3_env(monkeypatch)
    _login(client, real_session, role="viewer")
    version = _make_document_version(real_session)

    response = client.get(f"/v1/documents/{version.id}/signed-url")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in_seconds"] <= 300
    assert version.object_key in body["url"]


def test_signed_url_404s_for_an_unknown_document_version(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session, role="viewer")
    response = client.get(f"/v1/documents/{uuid.uuid4()}/signed-url")
    assert response.status_code == 404


def test_signed_url_issuance_is_audited(
    client: TestClient, real_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _restore_real_s3_env(monkeypatch)
    tenant = _login(client, real_session, role="viewer")
    version = _make_document_version(real_session)
    response = client.get(f"/v1/documents/{version.id}/signed-url")
    assert response.status_code == 200

    count = real_session.execute(
        text(
            "SELECT count(*) FROM audit_logs WHERE tenant_id = :tenant_id "
            "AND action = 'document_link_issued' AND target_id = :target_id"
        ),
        {"tenant_id": tenant.id, "target_id": str(version.id)},
    ).scalar()
    assert count == 1


def test_get_document_page_text_returns_the_real_raw_text(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session, role="viewer")
    version = _make_document_version(real_session)
    raw_text = "The real extracted page text, exactly as found in the filing."
    _make_document_page(real_session, version, raw_text)

    response = client.get(f"/v1/documents/{version.id}/pages/1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["raw_text"] == raw_text
    assert body["char_count"] == len(raw_text)


def test_get_document_page_text_404s_for_an_unknown_page(
    client: TestClient, real_session: Session
) -> None:
    _login(client, real_session, role="viewer")
    version = _make_document_version(real_session)
    response = client.get(f"/v1/documents/{version.id}/pages/1")
    assert response.status_code == 404
