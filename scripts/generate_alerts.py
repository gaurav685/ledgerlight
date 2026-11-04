"""Phase 5 §3: the real alerts-generation job. Evaluates every real,
active `alert_rules` row against new real events/scores for its own
watchlist's companies, creates real `alerts` rows, and triggers real
webhook deliveries for the owning tenant's active webhooks.

Runs as the owner DB role (bypasses RLS) -- a system job legitimately
needs cross-tenant visibility to evaluate every tenant's own rules in
one pass; the real `tenant_id` on every row it writes is what keeps
each tenant's own API view correctly scoped afterward.

Idempotent per (alert_rule, fact): a fact already present in some
existing alert's own `payload->>'event_id'` (or `'score_id'`) for
that rule is never re-alerted, so re-running this job is always
safe -- the same real discipline every other Phase 1-3 build script
in this project already follows.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ledgerlight.api import webhooks as webhooks_module  # noqa: E402
from ledgerlight.api.models import Alert  # noqa: E402
from ledgerlight.common.logging import configure_logging, get_logger  # noqa: E402
from ledgerlight.config.settings import Settings, load_settings  # noqa: E402
from ledgerlight.db.session import make_session_factory  # noqa: E402

logger = get_logger(__name__)


def _already_alerted_fact_ids(session: Session, alert_rule_id: uuid.UUID, key: str) -> set[str]:
    rows = session.execute(
        text("SELECT payload ->> :key FROM alerts WHERE alert_rule_id = :rule_id"),
        {"key": key, "rule_id": alert_rule_id},
    ).all()
    return {row[0] for row in rows if row[0] is not None}


def _watched_company_ids(session: Session, watchlist_id: uuid.UUID) -> list[uuid.UUID]:
    rows = session.execute(
        text("SELECT company_id FROM watchlist_items WHERE watchlist_id = :watchlist_id"),
        {"watchlist_id": watchlist_id},
    ).all()
    return [row[0] for row in rows]


def _evaluate_new_event_type(
    session: Session, rule_id: uuid.UUID, watchlist_id: uuid.UUID, config: dict[str, object]
) -> list[dict[str, object]]:
    event_type_code = config.get("event_type_code", "ANY")
    already = _already_alerted_fact_ids(session, rule_id, "event_id")
    company_ids = _watched_company_ids(session, watchlist_id)
    if not company_ids:
        return []

    rows = session.execute(
        text(
            """
            SELECT e.id, e.company_id, et.code, e.event_time, e.known_at, e.severity, e.status
            FROM events e
            JOIN event_types et ON et.id = e.event_type_id
            WHERE e.company_id = ANY(:company_ids)
              AND e.status IN ('candidate', 'verified')
              AND (CAST(:event_type_code AS TEXT) = 'ANY' OR et.code = :event_type_code)
            """
        ),
        {"company_ids": company_ids, "event_type_code": event_type_code},
    ).all()

    facts = []
    for row in rows:
        event_id = str(row[0])
        if event_id in already:
            continue
        facts.append(
            {
                "company_id": row[1],
                "payload": {
                    "fact": "new_event",
                    "event_id": event_id,
                    "event_type_code": row[2],
                    "event_time": row[3].isoformat() if row[3] else None,
                    "known_at": row[4].isoformat(),
                    "severity": row[5],
                    "tier": "VERIFIED" if row[6] == "verified" else "CANDIDATE",
                },
            }
        )
    return facts


def _evaluate_score_percentile_threshold(
    session: Session, rule_id: uuid.UUID, watchlist_id: uuid.UUID, config: dict[str, object]
) -> list[dict[str, object]]:
    min_percentile = float(config.get("min_percentile", 100))  # type: ignore[arg-type]
    already = _already_alerted_fact_ids(session, rule_id, "score_id")
    company_ids = _watched_company_ids(session, watchlist_id)
    if not company_ids:
        return []

    rows = session.execute(
        text(
            """
            SELECT id, company_id, as_of, model_name, model_version, calibrated_probability,
                   percentile
            FROM scores
            WHERE company_id = ANY(:company_ids) AND percentile >= :min_percentile
            """
        ),
        {"company_ids": company_ids, "min_percentile": min_percentile},
    ).all()

    facts = []
    for row in rows:
        score_id = str(row[0])
        if score_id in already:
            continue
        facts.append(
            {
                "company_id": row[1],
                "payload": {
                    "fact": "score_above_threshold",
                    "score_id": score_id,
                    "as_of": row[2].isoformat(),
                    "model_name": row[3],
                    "model_version": row[4],
                    "calibrated_probability": row[5],
                    "percentile": row[6],
                },
            }
        )
    return facts


def _deliver_to_tenant_webhooks(
    settings: Settings, session: Session, tenant_id: uuid.UUID, alert: Alert
) -> None:
    webhook_rows = session.execute(
        text(
            "SELECT id, url, secret_encrypted FROM webhooks "
            "WHERE tenant_id = :tenant_id AND is_active"
        ),
        {"tenant_id": tenant_id},
    ).all()
    payload_bytes = json.dumps(
        {"type": "alert", "alert_id": str(alert.id), "payload": alert.payload}
    ).encode("utf-8")
    for webhook_id, url, secret_encrypted in webhook_rows:
        secret = webhooks_module.decrypt_secret(settings, cast(str, secret_encrypted))
        result = webhooks_module.deliver_webhook(cast(str, url), secret, payload_bytes)
        session.execute(
            text(
                "INSERT INTO webhook_deliveries (id, tenant_id, webhook_id, alert_id, payload, "
                "signature, attempt_count, status, response_code, created_at) "
                "VALUES (gen_random_uuid(), :tenant_id, :webhook_id, :alert_id, :payload, "
                ":signature, :attempt_count, :status, :response_code, now())"
            ),
            {
                "tenant_id": tenant_id,
                "webhook_id": webhook_id,
                "alert_id": alert.id,
                "payload": json.dumps(alert.payload),
                "signature": webhooks_module.sign_payload(secret, payload_bytes, 0),
                "attempt_count": result.attempt,
                "status": "success" if result.success else "failed",
                "response_code": result.status_code,
            },
        )


def main() -> int:
    configure_logging()
    settings = load_settings()
    session = make_session_factory(settings)()
    created = 0
    try:
        rules = session.execute(
            text(
                "SELECT id, tenant_id, watchlist_id, rule_type, config "
                "FROM alert_rules WHERE is_active"
            )
        ).all()
        for raw_rule_id, raw_tenant_id, raw_watchlist_id, rule_type, raw_config in rules:
            rule_id = cast(uuid.UUID, raw_rule_id)
            tenant_id = cast(uuid.UUID, raw_tenant_id)
            watchlist_id = cast(uuid.UUID, raw_watchlist_id)
            config = cast("dict[str, object]", raw_config)
            if rule_type == "new_event_type":
                facts = _evaluate_new_event_type(session, rule_id, watchlist_id, config)
            elif rule_type == "score_percentile_threshold":
                facts = _evaluate_score_percentile_threshold(session, rule_id, watchlist_id, config)
            else:
                continue

            for fact in facts:
                alert = Alert(
                    tenant_id=tenant_id,
                    alert_rule_id=rule_id,
                    company_id=fact["company_id"],
                    payload=fact["payload"],
                )
                session.add(alert)
                session.flush()
                _deliver_to_tenant_webhooks(settings, session, tenant_id, alert)
                created += 1
        session.commit()
    except Exception:
        logger.exception("job_outcome", job="alert_generation", outcome="failed")
        raise
    finally:
        session.close()
    logger.info("job_outcome", job="alert_generation", outcome="success", alerts_created=created)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
