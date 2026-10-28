"""Background task entry points.

These open their own DB session (the request session is already closed when a
FastAPI BackgroundTask runs) and delegate to the pipeline. In this release
ingestion runs in-process via BackgroundTasks; the same functions can be driven
by an external worker (RQ/Celery/arq) without change.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db import SessionLocal
from app.models.document import Document
from app.services.ingestion import process_document, retry_document
from app.services.ingestion import _discard_source_file


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


def purge_indexed_source_files() -> None:
    """Clean up original uploads left by older versions after successful indexing."""
    db = SessionLocal()
    try:
        ids = db.execute(
            select(Document.id).where(
                Document.status == "indexed",
                Document.extracted_text != "",
                Document.storage_key != "",
            )
        ).scalars().all()
        for document_id in ids:
            doc = db.get(Document, document_id)
            if doc:
                _discard_source_file(db, doc)
    finally:
        db.close()
