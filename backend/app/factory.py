"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api.router import create_api_router
from .config import Settings, load_settings
from .database import migrate
from .services.whiteoutstats import WhiteoutStatsScheduler
from .services.calendar import renew_schedules

logger = logging.getLogger("vzn.api")


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or load_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        migrate(settings.database_path)
        scheduler = WhiteoutStatsScheduler(settings.database_path, settings)
        await scheduler.start()
        stop = asyncio.Event()
        async def renew_calendar():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(renew_schedules,settings.database_path)
                except Exception:
                    logger.exception("Calendar renewal failed")
                try:
                    await asyncio.wait_for(stop.wait(),timeout=3600)
                except TimeoutError:
                    pass
        renewal = asyncio.create_task(renew_calendar(),name="calendar-renewal")
        try:
            yield
        finally:
            stop.set()
            await renewal
            await scheduler.stop()

    app = FastAPI(
        title=settings.app_name,
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.include_router(create_api_router(settings))

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request contains invalid data.",
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            headers=error.headers,
            content={"error": {"code": f"http_{error.status_code}", "message": str(error.detail)}},
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, error: Exception) -> JSONResponse:
        logger.error(
            "Unhandled request error",
            extra={"path": request.url.path},
            exc_info=(type(error), error, error.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An internal error occurred."}},
        )

    return app
