"""Background task entry points.

These open their own DB session (the request session is already closed when a
FastAPI BackgroundTask runs) and delegate to the pipeline. In this release
ingestion runs in-process via BackgroundTasks; the same functions can be driven
by an external worker (RQ/Celery/arq) without change.
"""
from __future__ import annotations

from app.db import SessionLocal
from app.services.ingestion import process_document, retry_document


def run_ingestion(document_id: str) -> None:
    db = SessionLocal()
    try:
        process_document(db, document_id)
    finally:
        db.close()


def run_retry(document_id: str) -> None:
    db = SessionLocal()
    try:
        retry_document(db, document_id)
    finally:
        db.close()
