r"""Ingestion pipeline orchestration and its state machine.

State machine:
    PENDING -> FETCHING -> EXTRACTING -> INDEXING -> COMPLETED
                                                  \-> FAILED
Any stage may transition to FAILED (recorded, retryable) or CANCELLED.

A document is never marked ``indexed`` unless extraction AND embedding/indexing
succeeded. Failures are captured on both the job and the document.
"""
from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import Chunk, Document, IngestionJob
from app.services import extraction
from app.services.chunking import chunk_document
from app.services.embeddings import get_embedding_provider
from app.services.extraction import ExtractionError, ExtractionResult
from app.services.metadata import suggest_metadata
from app.services.storage import get_storage
from app.services.url_fetcher import FetchError, SsrfError, fetch_url
from app.services.vectorstore import (
    VectorPoint,
    encode_vector,
    get_qdrant,
    is_qdrant_enabled,
)

_URL_TYPES = {"url", "github", "twitter"}
logger = logging.getLogger(__name__)


def _discard_source_file(db: Session, doc: Document) -> None:
    """Keep the extracted knowledge; remove the original after it is safely indexed."""
    if not doc.storage_key:
        return
    key = doc.storage_key
    try:
        get_storage().delete(key)
    except Exception:
        logger.exception("Could not discard processed source file for document %s", doc.id)
        return
    doc.storage_key = ""
    db.add(doc)
    db.commit()


def _set_state(db: Session, job: IngestionJob, state: str, progress: float, detail: str = "") -> None:
    job.state = state
    job.progress = progress
    job.detail = detail
    db.add(job)
    db.commit()


def _fail(db: Session, job: IngestionJob, doc: Document, message: str) -> None:
    job.state = "FAILED"
    job.error = message[:4000]
    job.attempts += 1
    doc.status = "failed"
    doc.extraction_error = message[:4000]
    db.add_all([job, doc])
    db.commit()


def compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_duplicate(db: Session, org_id: str, content_hash: str, exclude_id: str) -> Document | None:
    if not content_hash:
        return None
    return db.execute(
        select(Document).where(
            Document.organization_id == org_id,
            Document.content_hash == content_hash,
            Document.id != exclude_id,
            Document.is_duplicate.is_(False),
            Document.status == "indexed",
        )
    ).scalars().first()


def _load_source_bytes(db: Session, job: IngestionJob, doc: Document) -> tuple[bytes, str]:
    """Return (raw_bytes, effective_source_type) for extraction."""
    if doc.source_type in _URL_TYPES:
        _set_state(db, job, "FETCHING", 0.15, f"Fetching {doc.source_url}")
        try:
            result = fetch_url(doc.source_url)
        except SsrfError as exc:
            raise ExtractionError(f"URL rejected by SSRF policy: {exc}") from exc
        except FetchError as exc:
            raise ExtractionError(f"Could not fetch URL: {exc}") from exc
        # Choose extractor by content type.
        ctype = result.content_type
        if "pdf" in ctype:
            return result.content, "pdf"
        if "html" in ctype or "xml" in ctype:
            return result.content, "html"
        return result.content, "txt"
    # Uploaded / stored source.
    if doc.storage_key:
        try:
            return get_storage().read(doc.storage_key), doc.source_type
        except FileNotFoundError:
            # A previous cleanup may have removed the upload before its DB
            # pointer was cleared; the extracted text remains authoritative.
            if doc.extracted_text:
                return doc.extracted_text.encode("utf-8"), "text"
            raise
    # Pasted text stored inline in extracted_text already.
    return doc.extracted_text.encode("utf-8"), "text"


def process_document(db: Session, document_id: str) -> None:
    """Run the full pipeline for a single document. Safe to call in a worker."""
    doc = db.get(Document, document_id)
    if doc is None:
        return
    job = db.execute(
        select(IngestionJob).where(IngestionJob.document_id == document_id)
    ).scalars().first()
    if job is None:
        job = IngestionJob(organization_id=doc.organization_id, document_id=doc.id, state="PENDING")
        db.add(job)
        db.commit()

    if job.state == "CANCELLED":
        return

    doc.status = "processing"
    db.add(doc)
    db.commit()

    try:
        # Once the original upload has been discarded, re-index from the
        # canonical extracted text retained in the knowledge pool.
        if doc.storage_key:
            raw, effective_type = _load_source_bytes(db, job, doc)
        elif doc.extracted_text and doc.source_type not in _URL_TYPES:
            raw, effective_type = doc.extracted_text.encode("utf-8"), "text"
        else:
            raw, effective_type = _load_source_bytes(db, job, doc)

        _set_state(db, job, "EXTRACTING", 0.4, "Extracting and normalizing content")
        if doc.source_type == "text" and effective_type == "text":
            result = ExtractionResult(text=doc.extracted_text, mime_type="text/plain")
        else:
            result = extraction.extract(effective_type, raw)

        text = result.text.strip()
        if not text:
            raise ExtractionError("Extraction produced no text")

        # Metadata the extractor discovered (don't overwrite user-provided).
        if not doc.title and result.title:
            doc.title = result.title[:500]
        if not doc.author and result.author:
            doc.author = result.author[:300]
        if result.mime_type:
            doc.mime_type = result.mime_type

        doc.extracted_text = text
        doc.content_hash = compute_content_hash(text.encode("utf-8"))
        doc.byte_size = len(raw)

        # Duplicate detection within the organization.
        dup = find_duplicate(db, doc.organization_id, doc.content_hash, doc.id)
        if dup is not None:
            doc.is_duplicate = True
            doc.duplicate_of_id = dup.id
            doc.status = "indexed"
            doc.chunk_count = 0
            db.add(doc)
            _set_state(db, job, "COMPLETED", 1.0, f"Duplicate of document {dup.id}")
            _discard_source_file(db, doc)
            return

        # Heuristic security metadata (model-independent).
        if not doc.summary:
            suggestion = suggest_metadata(doc.title, text)
            if suggestion.identifiers:
                doc.summary = "Identifiers: " + ", ".join(suggestion.identifiers[:15])

        _set_state(db, job, "INDEXING", 0.65, "Chunking and embedding")

        # Fresh re-index: drop any existing chunks first.
        for existing in list(doc.chunks):
            db.delete(existing)
        db.flush()

        chunks = chunk_document(result)
        if not chunks:
            raise ExtractionError("Chunking produced no chunks")

        provider = get_embedding_provider()
        vectors = provider.embed([c.text for c in chunks])
        if len(vectors) != len(chunks):
            raise ExtractionError("Embedding count mismatch")

        qpoints: list[VectorPoint] = []
        collection_ids = [c.id for c in doc.collections]
        for chunk, vec in zip(chunks, vectors):
            row = Chunk(
                document_id=doc.id,
                organization_id=doc.organization_id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                token_estimate=chunk.token_estimate,
                page_number=chunk.page_number,
                section_heading=chunk.section_heading,
                embedding=encode_vector(vec),
                embedding_model=provider.version,
            )
            db.add(row)
            db.flush()  # assign row.id
            qpoints.append(
                VectorPoint(
                    chunk_id=row.id,
                    document_id=doc.id,
                    organization_id=doc.organization_id,
                    collection_ids=collection_ids,
                    vector=vec,
                )
            )

        doc.chunk_count = len(chunks)
        doc.embedding_model = provider.model
        doc.embedding_version = provider.version
        doc.status = "indexed"
        doc.extraction_error = ""
        db.add(doc)
        db.commit()

        # The extracted text, chunks, and embeddings are now committed. Keep
        # those as the durable library and drop the bulky upload.
        _discard_source_file(db, doc)

        # Optional external vector store mirror.
        if is_qdrant_enabled():
            try:
                get_qdrant().upsert(qpoints)
            except Exception as exc:  # non-fatal: DB remains source of truth
                job.detail = f"indexed (qdrant mirror failed: {exc})"

        _set_state(db, job, "COMPLETED", 1.0, f"Indexed {len(chunks)} chunks")
    except Exception as exc:  # noqa: BLE001 - record any failure, keep retryable
        db.rollback()
        # Re-fetch to avoid stale state after rollback.
        doc = db.get(Document, document_id)
        job = db.execute(
            select(IngestionJob).where(IngestionJob.document_id == document_id)
        ).scalars().first()
        if doc and job:
            _fail(db, job, doc, str(exc))


def retry_document(db: Session, document_id: str) -> None:
    job = db.execute(
        select(IngestionJob).where(IngestionJob.document_id == document_id)
    ).scalars().first()
    if job and job.state in ("FAILED", "CANCELLED"):
        job.state = "PENDING"
        job.error = ""
        db.add(job)
        db.commit()
    process_document(db, document_id)
