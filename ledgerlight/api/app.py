"""Phase 5 §3: the real FastAPI application factory -- request-ID
middleware, and the one consistent error model every real endpoint's
failure goes through (never a raw stack trace to the client).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ledgerlight.api.metrics import metrics_endpoint, metrics_timing_middleware
from ledgerlight.api.rate_limit import RateLimitExceeded
from ledgerlight.api.routers import admin as admin_router
from ledgerlight.api.routers import alerts as alerts_router
from ledgerlight.api.routers import api_keys as api_keys_router
from ledgerlight.api.routers import auth as auth_router
from ledgerlight.api.routers import companies as companies_router
from ledgerlight.api.routers import documents as documents_router
from ledgerlight.api.routers import dossiers as dossiers_router
from ledgerlight.api.routers import health as health_router
from ledgerlight.api.routers import review as review_router
from ledgerlight.api.routers import watchlists as watchlists_router
from ledgerlight.api.routers import webhooks as webhooks_router
from ledgerlight.common.logging import configure_logging

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def create_app() -> FastAPI:
    # Phase 5 §8: real structured JSON logs to stdout -- this
    # infrastructure (ledgerlight.common.logging) existed since Phase 0
    # but was never actually called by any real entry point; the real
    # API process is the first to wire it in.
    configure_logging()

    app = FastAPI(
        title="Ledgerlight API", version="1.0", docs_url="/v1/docs", openapi_url="/v1/openapi.json"
    )

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Assigns one real request ID per request -- carried into
        every real audit_logs row and structured log line this
        request produces, and echoed back on the response so a client
        can report it."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(PermissionError)
    async def _permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": "forbidden",
                "detail": str(exc),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(int(exc.retry_after_seconds) + 1)},
            content={
                "error": "rate_limited",
                "detail": str(exc),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            headers=dict(exc.headers or {}),
            content={
                "error": "http_error",
                "detail": str(exc.detail),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """The real catch-all: logs the real exception server-side
        (with the request ID), but the client only ever sees a generic
        500 -- never a stack trace, never an internal message.

        A handler registered for the bare `Exception` class is wired
        by Starlette into `ServerErrorMiddleware`, the OUTERMOST layer,
        above every `@app.middleware("http")` below -- confirmed
        directly: on a real unhandled exception, it propagates through
        and past `_request_id_middleware`/`_security_headers_middleware`
        before this handler ever runs, so their own header mutations
        on the eventual response never take effect. The request ID and
        security headers are therefore set directly here instead."""
        request_id = getattr(request.state, "request_id", None)
        logger.exception("unhandled_exception", request_id=request_id)
        response = JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "an unexpected error occurred",
                "request_id": request_id,
            },
        )
        if request_id is not None:
            response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @app.middleware("http")
    async def _security_headers_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    app.middleware("http")(metrics_timing_middleware)

    @app.get("/metrics", include_in_schema=False)
    def _metrics() -> Response:
        return metrics_endpoint()

    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(companies_router.router)
    app.include_router(documents_router.router)
    app.include_router(dossiers_router.router)
    app.include_router(review_router.router)
    app.include_router(watchlists_router.router)
    app.include_router(alerts_router.router)
    app.include_router(api_keys_router.router)
    app.include_router(webhooks_router.router)
    app.include_router(admin_router.router)

    return app


app = create_app()
