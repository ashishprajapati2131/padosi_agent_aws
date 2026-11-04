"""Google Places Data Collector API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, auth, exports, history, places, search
from app.api import settings as settings_api
from app.config import get_settings
from app.database.connection import get_session_factory
from app.services.bootstrap import seed_admin
from app.services.errors import AppError
from app.utils.logger import log_event, setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    if settings.environment.lower() == "production":
        _ = settings.jwt_signing_key
    elif not (settings.jwt_secret or "").strip():
        log_event("info", "jwt_secret_missing")
    log_event(
        "info",
        "startup",
        field_mode=settings.google_places_field_mode,
        google_configured=bool((settings.google_maps_api_key or "").strip()),
        search_retention_days=settings.search_retention_days,
    )
    db = get_session_factory()()
    try:
        seed_admin(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    docs = None if settings.environment.lower() == "production" else "/docs"
    app = FastAPI(
        title="Google Places Data Collector",
        version="1.0.0",
        description="Search places matching your query through the Google Places API.",
        lifespan=lifespan,
        docs_url=docs,
        redoc_url=None if docs is None else "/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Export-Id"],
    )
    app.include_router(auth.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(places.router, prefix="/api")
    app.include_router(exports.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        current = get_settings()
        return {
            "status": "ok",
            "service": "google-places-collector",
            "google_configured": bool((current.google_maps_api_key or "").strip()),
        }

    @app.get("/")
    def root() -> dict:
        return {"service": "Google Places Data Collector", "health": "/api/health"}

    @app.exception_handler(AppError)
    async def app_error(_request: Request, exc: AppError) -> JSONResponse:
        body = {"detail": exc.message, "error_type": exc.error_type}
        if exc.search_id is not None:
            body["search_id"] = exc.search_id
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        parts: list[str] = []
        for err in exc.errors():
            loc = [str(item) for item in err.get("loc", []) if item not in {"body", "query"}]
            message = err.get("msg", "Invalid value")
            if loc:
                parts.append(f"{'.'.join(loc)}: {message}")
            else:
                parts.append(str(message))
        detail = " ".join(parts) or "The request is invalid."
        return JSONResponse(status_code=422, content={"detail": detail, "error_type": "invalid_request"})

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        log_event("error", "unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Please try again.", "error_type": "server_error"},
        )

    return app


app = create_app()
