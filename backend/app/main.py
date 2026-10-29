"""SecBrain FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    actions,
    apikeys,
    auth,
    chat,
    collections,
    dashboard,
    documents,
    drive_sync,
    health,
    knowledge,
    models,
    voice,
)
from app.config import settings
from app.services.tasks import purge_indexed_source_files

logging.basicConfig(
    level=logging.INFO,
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("secbrain")

app = FastAPI(
    title="SecBrain API",
    version="1.0.0",
    description="Model-independent cybersecurity knowledge platform.",
    docs_url="/docs",
    openapi_url="/api/v1/openapi.json",
)


@app.on_event("startup")
def discard_already_indexed_uploads() -> None:
    # The library keeps extracted text and chunks; the source files are no
    # longer needed once indexing has completed.
    purge_indexed_source_files()

if settings.cors_allow_all:
    # Bearer-header auth (no cookies) => wildcard origin with credentials off.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak internal tracebacks/secrets to clients.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


API_V1 = "/api/v1"
for module in (
    health,
    auth,
    collections,
    documents,
    drive_sync,
    knowledge,
    chat,
    models,
    apikeys,
    dashboard,
    voice,
    actions,
):
    app.include_router(module.router, prefix=API_V1)


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "api": API_V1}
