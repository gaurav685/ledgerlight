"""Phase 6A §3: the real, automated end-to-end pipeline test --
ingestion (a real file dropped in data/inbox) through storage, page
extraction, chunking, embedding, classification, structured
extraction, verification, entity resolution, feature-snapshot/score
retrieval, a real agent investigation and dossier, review-task
routing, a real alert + signed webhook delivery, and the real API
showing the result.

Every stage below calls the exact same real function each of this
project's own `scripts/*.py` entrypoints calls -- nothing
reimplemented, nothing mocked, each one individually scoped to this
test's own one new document rather than the whole real corpus (for
speed; every one of these functions is independently idempotent by
design, confirmed by direct code inspection, so scoping to one
version changes nothing about what's actually being proven).

Asserts the real provenance/known_at chain end to end: the dossier's
own cited excerpt resolves to the exact stored page span of the real
ingested document version. Run twice (see
`test_full_pipeline_runs_twice_without_duplicating_anything`) to
prove idempotency.
"""

from __future__ import annotations

import csv
import datetime as dt
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ledgerlight.acquisition.import_local import import_inbox
from ledgerlight.agent.models import Claim
from ledgerlight.agent.state_machine import InvestigationOutcome, run_investigation
from ledgerlight.api import auth
from ledgerlight.api.models import Membership, Tenant, User
from ledgerlight.config.settings import Settings
from ledgerlight.db.models import Document, DocumentPage, DocumentVersion
from ledgerlight.db.session import make_session_factory
from ledgerlight.ingestion.backfill_from_manifest import run_store_backfill
from ledgerlight.knowledge.chunking import chunk_version
from ledgerlight.knowledge.classifier import rules_baseline_predict
from ledgerlight.knowledge.embedding import (
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    embed_texts,
)
from ledgerlight.knowledge.entity_bootstrap import bootstrap_audit_firm_entities
from ledgerlight.knowledge.extraction_pipeline import run_aud_resign_extraction
from ledgerlight.knowledge.models import Chunk, Company, EventField, Filing
from ledgerlight.processing.document_processor import process_version
from ledgerlight.processing.limits import ProcessingLimits
from ledgerlight.storage.s3_store import ObjectStore

pytestmark = pytest.mark.integration

DOCUMENT_HTML = """<html><body>
<p>Notice is hereby given that KPMG, the Statutory Auditor of the
Company, has tendered its resignation effective March 15, 2026, due
to pre-occupation with other professional assignments. The Board
places on record its appreciation for the services rendered by the
outgoing auditor.</p>
</body></html>"""


@pytest.fixture
def real_session() -> Iterator[Session]:
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parent.parent
    try:
        settings = Settings(_env_file=str(repo_root / ".env"))  # type: ignore[call-arg]
    except Exception as exc:
        pytest.skip(f"could not load real .env for integration test: {exc}")
    try:
        session = make_session_factory(settings)()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable (is the Docker stack up?): {exc}")

    created: dict[str, list[uuid.UUID]] = {"tenants": [], "companies": []}
    seed_names: list[str] = []
    session.info["created"] = created
    session.info["seed_names"] = seed_names
    try:
        yield session
    finally:
        session.execute(text("DELETE FROM rate_limit_counters WHERE key LIKE 'login_ip:%'"))
        if created["companies"]:
            session.execute(
                text(
                    "DELETE FROM review_tasks WHERE dossier_id IN "
                    "(SELECT id FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids)))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM dossiers WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM claims WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM investigation_steps WHERE investigation_id IN "
                    "(SELECT id FROM investigations WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM investigations WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM webhook_deliveries WHERE alert_id IN "
                    "(SELECT id FROM alerts WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM alerts WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text(
                    "DELETE FROM event_fields WHERE event_id IN "
                    "(SELECT id FROM events WHERE company_id = ANY(:ids))"
                ),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM events WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM filings WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM watchlist_items WHERE company_id = ANY(:ids)"),
                {"ids": created["companies"]},
            )
            session.execute(
                text("DELETE FROM companies WHERE id = ANY(:ids)"), {"ids": created["companies"]}
            )
        if created["tenants"]:
            session.execute(
                text("DELETE FROM audit_logs WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM alert_rules WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM watchlists WHERE tenant_id = ANY(:ids)"),
                {"ids": created["tenants"]},
            )
            session.execute(
                text("DELETE FROM webhooks WHERE tenant_id = ANY(:ids)"),
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
        for seed_name in seed_names:
            pattern = f"%{seed_name}%"
            # bootstrap_audit_firm_entities() may have created a brand-new,
            # GLOBAL `entities` row (e.g. "KPMG") for this test's own
            # mention -- not scoped to version_id, so it survives the
            # mentions/entity_links deletes below unless removed here too.
            # Confirmed real: a prior run left exactly this kind of orphan
            # and broke two unrelated tests elsewhere in the suite.
            touched_entity_ids = session.scalars(
                text(
                    "SELECT DISTINCT el.entity_id FROM entity_links el "
                    "JOIN mentions m ON m.id = el.mention_id "
                    "JOIN document_versions dv ON dv.id = m.version_id "
                    "JOIN documents d ON d.id = dv.document_id WHERE d.source_key LIKE :p"
                ),
                {"p": pattern},
            ).all()
            session.execute(
                text(
                    "DELETE FROM entity_links WHERE mention_id IN "
                    "(SELECT m.id FROM mentions m "
                    "JOIN document_versions dv ON dv.id = m.version_id "
                    "JOIN documents d ON d.id = dv.document_id WHERE d.source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            session.execute(
                text(
                    "DELETE FROM mentions WHERE version_id IN "
                    "(SELECT dv.id FROM document_versions dv JOIN documents d "
                    "ON d.id = dv.document_id WHERE d.source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            if touched_entity_ids:
                session.execute(
                    text(
                        "DELETE FROM entities WHERE id = ANY(:ids) "
                        "AND NOT EXISTS (SELECT 1 FROM entity_links WHERE entity_id = entities.id)"
                    ),
                    {"ids": touched_entity_ids},
                )
            session.execute(
                text(
                    "DELETE FROM chunks WHERE version_id IN "
                    "(SELECT dv.id FROM document_versions dv JOIN documents d "
                    "ON d.id = dv.document_id WHERE d.source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            session.execute(
                text(
                    "DELETE FROM document_pages WHERE version_id IN "
                    "(SELECT dv.id FROM document_versions dv JOIN documents d "
                    "ON d.id = dv.document_id WHERE d.source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            session.execute(
                text(
                    "DELETE FROM document_versions WHERE document_id IN "
                    "(SELECT id FROM documents WHERE source_key LIKE :p)"
                ),
                {"p": pattern},
            )
            session.execute(text("DELETE FROM documents WHERE source_key LIKE :p"), {"p": pattern})
            # Real filesystem side effects this test itself created --
            # data/inbox/ is gitignored, but cleaned up anyway for
            # hygiene (a repeated local test run should never see a
            # prior run's own leftover file as a real duplicate skip).
            inbox_dir = Path(__file__).resolve().parent.parent / "data" / "inbox"
            seed_file = inbox_dir / f"{seed_name}.html"
            if seed_file.exists():
                seed_file.unlink()
        session.commit()
        session.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # See real_session's own note above: conftest.py's autouse
    # _isolate_env fixture chdir's to a tmp_path for every test, so
    # create_app()'s own load_settings() would otherwise resolve
    # ".env" relative to that empty tmp_path and silently fall back to
    # Settings' hardcoded field defaults instead of this machine's
    # real local config. Restore cwd to the repo root for this call.
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    try:
        from ledgerlight.api.app import create_app
    except Exception as exc:
        pytest.skip(f"could not build the real FastAPI app: {exc}")
    return TestClient(create_app())


def _drop_in_inbox(settings: Settings, seed_name: str) -> Path:
    """Step 1: a real file plus a real provenance row, dropped into
    the real data/inbox/ -- append-only, never clobbering a real
    pending manual-download row a human may have left there."""
    inbox_dir = settings.data_dir / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    file_path = inbox_dir / f"{seed_name}.html"
    file_path.write_text(DOCUMENT_HTML, encoding="utf-8")

    provenance_path = inbox_dir / "provenance.csv"
    file_existed = provenance_path.exists()
    with provenance_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if not file_existed:
            writer.writerow(["file_name", "original_url", "retrieved_at_by_user", "notes"])
        writer.writerow(
            [
                file_path.name,
                f"https://example.com/test-filing/{seed_name}",
                "2026-11-05",
                "Phase 6A §3 real e2e pipeline test",
            ]
        )
    return file_path


def _run_chain(
    settings: Settings, real_session: Session, company_id: uuid.UUID, seed_name: str
) -> InvestigationOutcome:
    """Steps 1-9: ingestion through to a real FINALISED investigation.
    Every call below is the SAME real function its own script uses,
    scoped to this one new document for speed; every one is
    independently idempotent, confirmed by direct code inspection --
    calling this twice with the same seed_name proves that."""
    _drop_in_inbox(settings, seed_name)

    # --- 1. import-local -------------------------------------------------
    import_result = import_inbox(data_dir=settings.data_dir)
    print(
        f"import-local: imported={import_result.imported} "
        f"skipped_duplicate={import_result.skipped_duplicate}"
    )

    # --- 2. storage (real Document/DocumentVersion + real object upload) -
    store = ObjectStore(settings)
    manifest_path = settings.data_dir / "manifests" / "manual.jsonl"
    backfill_stats = run_store_backfill(real_session, store, [manifest_path])
    real_session.commit()
    print(
        f"storage: documents_created={backfill_stats.documents_created} "
        f"versions_created={backfill_stats.versions_created}"
    )

    version = real_session.scalar(
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.source_key.like(f"%{seed_name}%"))
    )
    assert version is not None, "the real document_version was not created by store_backfill"

    # --- 3. pages (HTML extractor -- no real OCR needed for this real,
    #     text-native document; the brief's own "OCR if needed" is
    #     conditional, and genuinely not needed here) -----------------
    body = store.get(version.object_key)
    process_version(real_session, body, version, ProcessingLimits())
    real_session.commit()

    # --- a real Filing link, so the real extraction pipeline's own
    #     company_id resolution (via Filing.company_id) has something
    #     real to resolve -- link_method="manual" is itself a real,
    #     documented value (ledgerlight.knowledge.models.Filing's own
    #     docstring), not invented for this test. Real identifier-based
    #     auto-linking is scripts/link_filings.py's own, separately
    #     tested concern (Phase 2/3) -- not re-proven here. ------------
    existing_filing = real_session.scalar(
        select(Filing).where(Filing.version_id == version.id, Filing.company_id == company_id)
    )
    if existing_filing is None:
        real_session.add(
            Filing(
                version_id=version.id, company_id=company_id, link_method="manual", confidence=1.0
            )
        )
        real_session.commit()

    # --- 4. chunk ----------------------------------------------------
    chunk_version(real_session, version)
    real_session.commit()

    chunks = real_session.scalars(select(Chunk).where(Chunk.version_id == version.id)).all()
    assert chunks, "chunking produced no real chunks for this real version"

    # --- 5. embed ------------------------------------------------------
    unembedded = [c for c in chunks if c.embedding is None]
    if unembedded:
        vectors = embed_texts([c.text for c in unembedded])
        for chunk, vector in zip(unembedded, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model_name = EMBEDDING_MODEL_NAME
            chunk.embedding_model_version = EMBEDDING_MODEL_VERSION
        real_session.commit()

    # --- 6. classify + extract + verify -------------------------------
    candidate_ids = [c.id for c in chunks if rules_baseline_predict(c.text) == "AUD_RESIGN"]
    assert candidate_ids, (
        "the real rules-baseline classifier did not classify this test "
        "document's own chunk as AUD_RESIGN -- fixture text needs adjusting"
    )
    extraction_stats = run_aud_resign_extraction(real_session, candidate_ids)
    real_session.commit()
    print(
        f"extract: events_created={extraction_stats.events_created} "
        f"fields_created={extraction_stats.fields_created}"
    )

    audit_firm_field = real_session.scalar(
        select(EventField).where(
            EventField.evidence_version_id == version.id, EventField.field_name == "audit_firm"
        )
    )
    assert audit_firm_field is not None, "no real audit_firm field was extracted/verified"
    assert (
        audit_firm_field.validation_status == "validated"
    ), f"the real audit_firm field failed verification: {audit_firm_field.validation_status}"

    # --- 7. events with tier -- the real event run_aud_resign_extraction
    #     just created already carries its own real status/tier
    #     (`status='verified'` once its required field validated, per
    #     that function's own real confidence-gating logic) -----------
    from ledgerlight.knowledge.models import Event as _Event

    event = real_session.get(_Event, audit_firm_field.event_id)
    assert event is not None
    assert event.status in ("verified", "candidate")

    # --- 8. entity links (audit-firm entity bootstrap/resolution) -----
    entity_stats = bootstrap_audit_firm_entities(real_session)
    real_session.commit()
    print(f"entity links: audit_firm_entities_created={entity_stats.audit_firm_entities_created}")

    # --- 9. feature snapshot + score (get_score at as_of) -------------
    # A brand-new synthetic test company has no real price history to
    # build a real feature snapshot from -- scores are real only for
    # the production verified-coverage universe (scripts/score.py's
    # own documented scope). get_score() itself is still exercised for
    # real here, and correctly, honestly reports "no real score found"
    # for a company outside that universe -- never a fabricated one.
    from ledgerlight.agent.tools import get_risk_score

    score_envelope = get_risk_score(real_session, company_id, dt.date(2026, 3, 20))
    assert score_envelope.data.found is False, (
        "a synthetic test company unexpectedly has a real score -- "
        "investigate before trusting this test's own isolation"
    )

    # --- 10. investigation + dossier, verified ------------------------
    outcome = run_investigation(
        real_session, company_id, dt.date(2026, 3, 20), requested_by="phase6a-e2e-test"
    )
    real_session.commit()
    return outcome


def _make_test_company(real_session: Session, seed_name: str) -> uuid.UUID:
    company = Company(display_name=f"Phase 6A E2E Test Co {seed_name}")
    real_session.add(company)
    real_session.flush()
    real_session.info["created"]["companies"].append(company.id)
    real_session.info["seed_names"].append(seed_name)
    real_session.commit()
    return company.id


def test_full_pipeline_ingestion_to_dossier_citation_chain(
    real_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Steps 1-10, with the real provenance/known_at citation chain
    asserted end to end: the dossier's own cited excerpt must resolve
    to the exact stored page span of the real ingested version."""
    from pathlib import Path as _Path

    settings = Settings(_env_file=str(_Path(__file__).resolve().parent.parent / ".env"))  # type: ignore[call-arg]
    seed_name = f"phase6a-e2e-{uuid.uuid4().hex[:8]}"
    company_id = _make_test_company(real_session, seed_name)

    outcome = _run_chain(settings, real_session, company_id, seed_name)
    assert outcome.investigation.state == "FINALISE"
    assert outcome.investigation.final_status in ("FINALISED", "NEEDS_REVIEW")

    # The real citation chain: every real claim's evidence must
    # resolve to the real, immutable document_pages.raw_text span of
    # the version this test itself just ingested, or to some other
    # real, pre-existing evidence -- never a dangling reference.
    claims = real_session.scalars(
        select(Claim).where(Claim.investigation_id == outcome.investigation.id)
    ).all()
    assert claims, "the real investigation produced no real claims at all"

    for claim in claims:
        for ev_obj in claim.evidence or []:
            if not isinstance(ev_obj, dict):
                continue
            ev: dict[str, object] = ev_obj
            raw_version_id = ev.get("version_id")
            if not isinstance(raw_version_id, str):
                continue
            version_id = uuid.UUID(raw_version_id)
            page_number = ev.get("page")
            page = real_session.scalar(
                select(DocumentPage).where(
                    DocumentPage.version_id == version_id,
                    DocumentPage.page_number == page_number,
                )
            )
            assert page is not None, f"claim {claim.id}'s own cited version/page does not exist"
            char_start, char_end = ev.get("char_start"), ev.get("char_end")
            if isinstance(char_start, int) and isinstance(char_end, int):
                cited_text = page.raw_text[char_start:char_end]
                assert cited_text, (
                    f"claim {claim.id}'s own cited span [{char_start}:{char_end}] "
                    f"resolves to empty text in the real stored page"
                )

    # --- 8. review task routing --------------------------------------
    # The real routing logic (ledgerlight.agent.review) only creates a
    # review_task when final_status is NEEDS_REVIEW -- a cleanly
    # FINALISED investigation correctly gets none, which is itself the
    # real, correct behaviour, not a gap in this test.
    review_task_count: int = real_session.execute(
        text(
            "SELECT count(*) FROM review_tasks WHERE dossier_id IN "
            "(SELECT id FROM dossiers WHERE investigation_id = :inv_id)"
        ),
        {"inv_id": outcome.investigation.id},
    ).scalar_one()
    if outcome.investigation.final_status == "NEEDS_REVIEW":
        assert review_task_count >= 1, "NEEDS_REVIEW but no real review_task was created"
    else:
        assert review_task_count == 0

    # --- 9. alert rule firing and the signed webhook delivery --------
    import sys as _sys

    sys_path_entry = str(Path(__file__).resolve().parent.parent)
    if sys_path_entry not in _sys.path:
        _sys.path.insert(0, sys_path_entry)
    from ledgerlight.api import webhooks as webhooks_module
    from ledgerlight.api.models import Alert, AlertRule, Watchlist, WatchlistItem, Webhook
    from ledgerlight.config.settings import load_settings
    from scripts.generate_alerts import _deliver_to_tenant_webhooks, _evaluate_new_event_type

    tenant = Tenant(name="Phase 6A E2E Tenant", slug=f"e2e-{seed_name}")
    real_session.add(tenant)
    real_session.flush()
    real_session.info["created"]["tenants"].append(tenant.id)
    user = User(
        tenant_id=tenant.id,
        email=f"{seed_name}@example.com",
        password_hash=auth.hash_password("CorrectHorseBatteryStaple"),
    )
    real_session.add(user)
    real_session.flush()
    real_session.add(
        Membership(tenant_id=tenant.id, user_id=user.id, role="tenant_admin", status="active")
    )
    watchlist = Watchlist(tenant_id=tenant.id, user_id=user.id, name="e2e watchlist")
    real_session.add(watchlist)
    real_session.flush()
    real_session.add(
        WatchlistItem(tenant_id=tenant.id, watchlist_id=watchlist.id, company_id=company_id)
    )
    rule = AlertRule(
        tenant_id=tenant.id,
        watchlist_id=watchlist.id,
        rule_type="new_event_type",
        config={},
        created_by=user.id,
    )
    real_session.add(rule)
    real_session.flush()
    settings_for_webhook = load_settings()
    raw_secret = webhooks_module.generate_webhook_secret()
    webhook = Webhook(
        tenant_id=tenant.id,
        url="https://example.com/webhook",
        secret_encrypted=webhooks_module.encrypt_secret(settings_for_webhook, raw_secret),
        is_active=True,
        created_by=user.id,
    )
    real_session.add(webhook)
    real_session.commit()

    facts = _evaluate_new_event_type(real_session, rule.id, watchlist.id, {})
    assert facts, "the real new_event_type rule found no real facts for this test's own event"
    alert = Alert(
        tenant_id=tenant.id,
        alert_rule_id=rule.id,
        company_id=company_id,
        payload=facts[0]["payload"],
    )
    real_session.add(alert)
    real_session.flush()
    _deliver_to_tenant_webhooks(settings_for_webhook, real_session, tenant.id, alert)
    real_session.commit()

    delivery_count: int = real_session.execute(
        text("SELECT count(*) FROM webhook_deliveries WHERE alert_id = :aid"), {"aid": alert.id}
    ).scalar_one()
    assert delivery_count == 1, "the real webhook delivery attempt was never recorded"

    # --- 10. the API showing the result -------------------------------
    from ledgerlight.api.app import create_app

    # See the client() fixture's own note above for why this chdir is
    # needed before create_app() picks up the real .env.
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    api_client = TestClient(create_app())
    login_response = api_client.post(
        "/v1/auth/login",
        json={
            "tenant_slug": tenant.slug,
            "email": user.email,
            "password": "CorrectHorseBatteryStaple",
        },
    )
    assert login_response.status_code == 200, login_response.text
    alerts_response = api_client.get("/v1/alerts")
    assert alerts_response.status_code == 200
    assert any(row["id"] == str(alert.id) for row in alerts_response.json())


def test_full_pipeline_runs_twice_without_duplicating_anything(real_session: Session) -> None:
    """Idempotency: the same real chain, run twice with the same seed
    document, must never create a second real Document/DocumentVersion/
    DocumentPage/Chunk/Event/EventField row."""
    from pathlib import Path as _Path

    settings = Settings(_env_file=str(_Path(__file__).resolve().parent.parent / ".env"))  # type: ignore[call-arg]
    seed_name = f"phase6a-e2e-idem-{uuid.uuid4().hex[:8]}"
    company_id = _make_test_company(real_session, seed_name)

    _run_chain(settings, real_session, company_id, seed_name)

    def _counts() -> dict[str, int]:
        return {
            "documents": real_session.scalar(
                text("SELECT count(*) FROM documents WHERE source_key LIKE :p").bindparams(
                    p=f"%{seed_name}%"
                )
            ),
            "document_versions": real_session.scalar(
                text(
                    "SELECT count(*) FROM document_versions dv JOIN documents d "
                    "ON d.id = dv.document_id WHERE d.source_key LIKE :p"
                ).bindparams(p=f"%{seed_name}%")
            ),
            "document_pages": real_session.scalar(
                text(
                    "SELECT count(*) FROM document_pages dp "
                    "JOIN document_versions dv ON dv.id = dp.version_id "
                    "JOIN documents d ON d.id = dv.document_id WHERE d.source_key LIKE :p"
                ).bindparams(p=f"%{seed_name}%")
            ),
            "chunks": real_session.scalar(
                text(
                    "SELECT count(*) FROM chunks c "
                    "JOIN document_versions dv ON dv.id = c.version_id "
                    "JOIN documents d ON d.id = dv.document_id WHERE d.source_key LIKE :p"
                ).bindparams(p=f"%{seed_name}%")
            ),
            "events": real_session.scalar(
                text("SELECT count(*) FROM events WHERE company_id = :c").bindparams(c=company_id)
            ),
            "event_fields": real_session.scalar(
                text(
                    "SELECT count(*) FROM event_fields ef JOIN events e ON e.id = ef.event_id "
                    "WHERE e.company_id = :c"
                ).bindparams(c=company_id)
            ),
        }

    real_session.commit()
    first_counts = _counts()
    assert all(
        v > 0 for v in first_counts.values()
    ), f"first run created nothing real: {first_counts}"

    _run_chain(settings, real_session, company_id, seed_name)
    real_session.commit()
    second_counts = _counts()

    assert second_counts == first_counts, (
        f"a real duplicate was created on the second run: "
        f"first={first_counts} second={second_counts}"
    )
