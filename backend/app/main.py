"""SecBrain FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    apikeys,
    auth,
    chat,
    collections,
    dashboard,
    documents,
    health,
    knowledge,
    models,
)
from app.config import settings

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
    knowledge,
    chat,
    models,
    apikeys,
    dashboard,
):
    app.include_router(module.router, prefix=API_V1)


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "api": API_V1}
