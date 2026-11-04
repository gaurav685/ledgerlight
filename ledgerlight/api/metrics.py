"""Phase 5 §8: real Prometheus metrics -- request count and latency,
labelled by real method/route/status, never by anything high-
cardinality (no raw path params, no tenant_id -- a real tenant_id
label would blow up cardinality under `prometheus_client`'s own
in-memory collector with every new real tenant)."""

from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "ledgerlight_http_requests_total",
    "Total real HTTP requests handled",
    ["method", "route", "status_code"],
)
REQUEST_DURATION_SECONDS = Histogram(
    "ledgerlight_http_request_duration_seconds",
    "Real HTTP request duration in seconds",
    ["method", "route"],
)
JOB_OUTCOMES = Counter(
    "ledgerlight_job_outcomes_total",
    "Real outcomes of background jobs run inside this process",
    ["job", "outcome"],
)


def _real_route_template(request: Request) -> str:
    """The real matched route PATTERN (e.g. `/v1/companies/{company_id}`),
    never the real raw path (which would contain a real company_id/
    investigation_id -- unbounded cardinality, and arguably sensitive).
    Falls back to the raw path only for a genuinely unmatched route
    (a real 404 before routing resolves anything)."""
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return str(route.path)
    return request.url.path


async def metrics_timing_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    route = _real_route_template(request)
    REQUEST_COUNT.labels(
        method=request.method, route=route, status_code=str(response.status_code)
    ).inc()
    REQUEST_DURATION_SECONDS.labels(method=request.method, route=route).observe(duration)
    return response


def metrics_endpoint() -> Response:
    """The real `/metrics` endpoint -- plain-text Prometheus exposition
    format. Deliberately unauthenticated (matches real Prometheus
    scraping convention) but never routed through the public ALB
    listener in `infra/aws/alb.tf` -- internal-network-only in any
    real deployment, same as the brief's own requirement."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
