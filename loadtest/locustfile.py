"""Phase 6A §8: a real, small-scale API load test against the local
stack's key read endpoints (company search/overview/events/timeline/
scores, watchlists, alerts). Scale is deliberately small -- this
host's own real memory has been repeatedly unstable during this
project's own work (see docs/phase-6/progress.md), so this models a
handful of concurrent analysts, not a production-scale burst.

Logs in ONCE (class-level shared session cookie) rather than per
simulated user: the real login endpoint rate-limits to 10/minute per
client IP (ledgerlight/api/routers/auth.py), and every simulated user
here shares one IP (localhost) -- logging in per-user would just
exercise that rate limiter, not the read endpoints this test is
actually for.

Usage:
    uv run locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \
        --users 5 --spawn-rate 1 --run-time 60s --headless \
        --csv docs/phase-6/evidence/sec08-loadtest
"""

from __future__ import annotations

import threading

from locust import HttpUser, between, task

TENANT_SLUG = "test-tenant-a"
# "analyst" (not "viewer"): watchlists/alerts need rbac.MANAGE_OWN_WATCHLISTS,
# which "viewer" genuinely doesn't have (correct RBAC, confirmed by a real
# 403 on the first run of this test) -- analyst has it alongside view access.
LOGIN_EMAIL = "analyst@test-tenant-a.test"
LOGIN_PASSWORD = "LedgerlightTest123!"  # noqa: S105 -- a real, fixed, public TEST credential
REAL_COMPANY_ID = "c3f1cd29-fd6b-4c6f-963e-b83710203c9e"  # GENSOL
# GENSOL's only real score is at 2025-03-31 -- an earlier as_of correctly
# 404s ("no real score found at or before this date"), confirmed by the
# first run of this test. Use a date at/after the real score.
AS_OF = "2025-12-31"

_login_lock = threading.Lock()
_shared_cookie: str | None = None


class AnalystReadUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        global _shared_cookie
        with _login_lock:
            if _shared_cookie is None:
                response = self.client.post(
                    "/v1/auth/login",
                    json={
                        "tenant_slug": TENANT_SLUG,
                        "email": LOGIN_EMAIL,
                        "password": LOGIN_PASSWORD,
                    },
                    name="/v1/auth/login (once, shared)",
                )
                response.raise_for_status()
                _shared_cookie = response.cookies.get("ll_session")
        if _shared_cookie:
            self.client.cookies.set("ll_session", _shared_cookie)

    @task(3)
    def search_companies(self) -> None:
        self.client.get("/v1/companies/search?q=GENSOL", name="/v1/companies/search")

    @task(5)
    def get_company(self) -> None:
        self.client.get(f"/v1/companies/{REAL_COMPANY_ID}", name="/v1/companies/{id}")

    @task(4)
    def get_events(self) -> None:
        self.client.get(
            f"/v1/companies/{REAL_COMPANY_ID}/events?as_of={AS_OF}",
            name="/v1/companies/{id}/events",
        )

    @task(4)
    def get_timeline(self) -> None:
        self.client.get(
            f"/v1/companies/{REAL_COMPANY_ID}/timeline?as_of={AS_OF}",
            name="/v1/companies/{id}/timeline",
        )

    @task(3)
    def get_scores(self) -> None:
        self.client.get(
            f"/v1/companies/{REAL_COMPANY_ID}/scores?as_of={AS_OF}",
            name="/v1/companies/{id}/scores",
        )

    @task(2)
    def get_watchlists(self) -> None:
        self.client.get("/v1/watchlists", name="/v1/watchlists")

    @task(2)
    def get_alerts(self) -> None:
        self.client.get("/v1/alerts", name="/v1/alerts")
