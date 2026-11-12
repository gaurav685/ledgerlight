"""Phase 5 §3: real end-to-end test for scripts/generate_alerts.py --
a real watched company's real new event produces a real Alert row and
a real, signed webhook delivery (mocked via respx against
https://1.1.1.1/hook, same pattern as tests/test_api_webhooks.py);
re-running the same job a second time creates no duplicate alert,
proving the real idempotency the module's own docstring promises.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx
from httpx import Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.api import auth
from ledgerlight.api import webhooks as webhooks_module
from ledgerlight.api.models import Alert, AlertRule, Tenant, User, Watchlist, WatchlistItem, Webhook
from ledgerlight.config.settings import Settings
from ledgerlight.db.session import make_session_factory
from ledgerlight.knowledge.models import Company, Event, EventType

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "generate_alerts", REPO_ROOT / "scripts" / "generate_alerts.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["generate_alerts"] = _MODULE
_SPEC.loader.exec_module(_MODULE)


@pytest.fixture
def real_session() -> Iterator[Session]:
    try:
        settings = Settings(_env_file=str(REPO_ROOT / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")
    try:
        session = make_session_factory(settings)()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    created: dict[str, list[uuid.UUID]] = {"tenants": [], "companies": []}
    session.info["created"] = created
    try:
        yield session
    finally:
        if created["tenants"]:
            session.execute(
                text("DELETE FROM webhook_deliveries WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM alerts WHERE tenant_id = ANY(:ids)"), {"ids": created["tenants"]}
            )
            session.execute(
                text("DELETE FROM alert_rules WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM webhooks WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM watchlist_items WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM watchlists WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM users WHERE tenant_id = ANY(:ids)"), {"ids": created["tenants"]}
            )
        if created["companies"]:
            session.execute(
                text("DELETE FROM events WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created["companies"]}
            )
        if created["tenants"]:
            session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": created["tenants"]}
            )
        session.commit()
        session.close()


def test_a_new_event_produces_one_real_alert_and_a_signed_webhook_delivery(
    real_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # conftest.py's autouse _isolate_env fixture chdir's to a tmp_path
    # for every test, so generate_alerts.py's own main() (which calls
    # load_settings() independently, with no override hook) would
    # otherwise resolve ".env" relative to that empty tmp_path and
    # fall back to Settings' hardcoded postgres_port default instead
    # of this machine's real local port. Restore cwd to the repo root.
    monkeypatch.chdir(REPO_ROOT)
    tenant = Tenant(name="Alerts Job Test Co", slug=f"alerts-job-{uuid.uuid4().hex[:8]}")
    real_session.add(tenant)
    real_session.flush()
    real_session.info["created"]["tenants"].append(tenant.id)

    company = Company(display_name=f"Alerts Job Target {uuid.uuid4().hex[:8]}")
    real_session.add(company)
    real_session.flush()
    real_session.info["created"]["companies"].append(company.id)

    user = User(
        tenant_id=tenant.id,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=auth.hash_password("CorrectHorseBatteryStaple"),
    )
    real_session.add(user)
    real_session.flush()

    watchlist = Watchlist(tenant_id=tenant.id, user_id=user.id, name="Watch")
    real_session.add(watchlist)
    real_session.flush()
    real_session.add(
        WatchlistItem(tenant_id=tenant.id, watchlist_id=watchlist.id, company_id=company.id)
    )

    settings = Settings(_env_file=str(REPO_ROOT / ".env"))  # type: ignore[call-arg]
    raw_secret = webhooks_module.generate_webhook_secret()
    webhook = Webhook(
        tenant_id=tenant.id,
        url="https://1.1.1.1/hook",
        secret_encrypted=webhooks_module.encrypt_secret(settings, raw_secret),
        created_by=user.id,
    )
    real_session.add(webhook)

    rule = AlertRule(
        tenant_id=tenant.id,
        watchlist_id=watchlist.id,
        rule_type="new_event_type",
        config={"event_type_code": "ANY"},
        created_by=user.id,
    )
    real_session.add(rule)
    real_session.flush()

    event_type = real_session.scalar(select(EventType).where(EventType.code == "AUD_RESIGN"))
    assert event_type is not None, "real taxonomy event type AUD_RESIGN must already exist"
    event = Event(
        event_type_id=event_type.id,
        company_id=company.id,
        known_at=dt.datetime.now(dt.UTC),
        severity="medium",
        status="verified",
        detector_name="test",
        detector_version="1",
        confidence=0.9,
    )
    real_session.add(event)
    real_session.commit()

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://1.1.1.1/hook").mock(return_value=Response(200))
        exit_code = _MODULE.main()
    assert exit_code == 0

    alerts = real_session.scalars(select(Alert).where(Alert.alert_rule_id == rule.id)).all()
    assert len(alerts) == 1
    assert alerts[0].payload["event_id"] == str(event.id)

    delivery_status = real_session.execute(
        text("SELECT status FROM webhook_deliveries WHERE alert_id = :alert_id"),
        {"alert_id": alerts[0].id},
    ).scalar()
    assert delivery_status == "success"

    # Re-running the job must never create a duplicate alert for the
    # same real fact -- the real idempotency the module promises.
    with respx.mock(assert_all_called=False):
        second_exit_code = _MODULE.main()
    assert second_exit_code == 0
    alerts_after_rerun = real_session.scalars(
        select(Alert).where(Alert.alert_rule_id == rule.id)
    ).all()
    assert len(alerts_after_rerun) == 1
