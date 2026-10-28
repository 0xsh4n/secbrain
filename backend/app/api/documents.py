from __future__ import annotations

from datetime import timedelta

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, require_session
from app.config import settings
from app.db import get_db
from app.models.collection import Collection, Tag, document_collections
from app.models.document import Document, IngestionJob
from app.models.mixins import utcnow
from app.schemas.common import iso
from app.schemas.document import (
    DocumentOut,
    DocumentUpdate,
    JobOut,
    TextIngestRequest,
    UrlIngestRequest,
)
from app.services import audit
from app.services.permissions import (
    accessible_collection_ids,
    can_read_document,
    can_write_document,
)
from app.services.tasks import run_ingestion, run_retry
from app.services.vectorstore import get_qdrant, is_qdrant_enabled

router = APIRouter(prefix="/documents", tags=["documents"])

_EXT_TO_TYPE = {
    "pdf": "pdf",
    "txt": "txt",
    "text": "txt",
    "md": "markdown",
    "markdown": "markdown",
    "html": "html",
    "htm": "html",
    "docx": "docx",
}


def _serialize(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        source_type=doc.source_type,
        source_url=doc.source_url,
        author=doc.author,
        status=doc.status,
        chunk_count=doc.chunk_count,
        byte_size=doc.byte_size,
        content_hash=doc.content_hash,
        is_duplicate=doc.is_duplicate,
        duplicate_of_id=doc.duplicate_of_id,
        extraction_error=doc.extraction_error,
        embedding_model=doc.embedding_model,
        embedding_version=doc.embedding_version,
        summary=doc.summary,
        collection_ids=[c.id for c in doc.collections],
        tags=[t.name for t in doc.tags],
        created_at=iso(doc.created_at),
        updated_at=iso(doc.updated_at),
    )


def _serialize_job(job: IngestionJob) -> JobOut:
    return JobOut(
        id=job.id,
        document_id=job.document_id,
        state=job.state,
        progress=job.progress,
        detail=job.detail,
        error=job.error,
        attempts=job.attempts,
        created_at=iso(job.created_at),
        updated_at=iso(job.updated_at),
    )


def _resolve_collections(db: Session, principal: Principal, ids: list[str]) -> list[Collection]:
    if not ids:
        return []
    accessible = accessible_collection_ids(db, principal.user)
    if principal.is_api and principal.scoped_collection_ids:
        accessible &= set(principal.scoped_collection_ids)
    resolved: list[Collection] = []
    for cid in ids:
        if cid not in accessible:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"No access to collection {cid}"
            )
        c = db.get(Collection, cid)
        if c is not None:
            resolved.append(c)
    return resolved


def _create_and_queue(
    db: Session,
    principal: Principal,
    background: BackgroundTasks,
    *,
    title: str,
    source_type: str,
    source_url: str = "",
    storage_key: str = "",
    mime_type: str = "",
    inline_text: str = "",
    collection_ids: list[str],
    byte_size: int = 0,
) -> Document:
    collections = _resolve_collections(db, principal, collection_ids)
    doc = Document(
        organization_id=principal.user.organization_id,
        owner_id=principal.user.id,
        title=title,
        source_type=source_type,
        source_url=source_url,
        storage_key=storage_key,
        mime_type=mime_type,
        extracted_text=inline_text,
        byte_size=byte_size,
        status="pending",
    )
    doc.collections = collections
    db.add(doc)
    db.flush()
    db.add(IngestionJob(organization_id=doc.organization_id, document_id=doc.id, state="PENDING"))
    db.commit()
    audit.record(
        db,
        organization_id=doc.organization_id,
        action="document.ingest",
        actor_type=principal.auth_type,
        actor_id=principal.user.id,
        resource_type="document",
        resource_id=doc.id,
        detail=f"type={source_type}",
    )
    background.add_task(run_ingestion, doc.id)
    return doc


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    collection_ids: str = Form(default=""),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    from app.services.storage import get_storage

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Empty file")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    source_type = _EXT_TO_TYPE.get(ext)
    if source_type is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unsupported file type: .{ext} (allowed: pdf, txt, md, html, docx)",
        )
    coll_ids = [c for c in collection_ids.split(",") if c.strip()]
    storage_key = f"{principal.user.organization_id}/{file.filename}-{utcnow().timestamp()}"
    get_storage().save(storage_key, data)
    doc = _create_and_queue(
        db,
        principal,
        background,
        title=title or (file.filename or "Uploaded document"),
        source_type=source_type,
        storage_key=storage_key,
        mime_type=file.content_type or "",
        collection_ids=coll_ids,
        byte_size=len(data),
    )
    return _serialize(doc)


@router.post("/text", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def ingest_text(
    payload: TextIngestRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    doc = _create_and_queue(
        db,
        principal,
        background,
        title=payload.title or "Pasted text",
        source_type=payload.source_type,
        inline_text=payload.text,
        collection_ids=payload.collection_ids,
        byte_size=len(payload.text.encode("utf-8")),
    )
    return _serialize(doc)


@router.post("/url", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def ingest_url(
    payload: UrlIngestRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    doc = _create_and_queue(
        db,
        principal,
        background,
        title=payload.title,
        source_type=payload.source_type,
        source_url=str(payload.url),
        collection_ids=payload.collection_ids,
    )
    return _serialize(doc)


@router.get("", response_model=dict)
def list_documents(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    source_type: str | None = None,
    collection_id: str | None = None,
    q: str | None = None,
    sort: str = Query(default="created_desc"),
):
    user = principal.user
    accessible = accessible_collection_ids(db, user)
    if principal.is_api and principal.scoped_collection_ids:
        accessible &= set(principal.scoped_collection_ids)

    stmt = select(Document).where(Document.organization_id == user.organization_id)
    # Access scope: owned OR in an accessible collection (admins see all org docs,
    # but API keys are always constrained to their scope / accessible set).
    if principal.is_api or not user.is_admin:
        coll_docs = select(document_collections.c.document_id).where(
            document_collections.c.collection_id.in_(accessible or [""])
        )
        from sqlalchemy import or_

        clause = Document.id.in_(coll_docs)
        if not principal.is_api:
            clause = or_(Document.owner_id == user.id, clause)
        stmt = stmt.where(clause)

    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    if source_type:
        stmt = stmt.where(Document.source_type == source_type)
    if collection_id:
        stmt = stmt.where(
            Document.id.in_(
                select(document_collections.c.document_id).where(
                    document_collections.c.collection_id == collection_id
                )
            )
        )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Document.title).like(like))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    order = {
        "created_desc": Document.created_at.desc(),
        "created_asc": Document.created_at.asc(),
        "title_asc": Document.title.asc(),
        "title_desc": Document.title.desc(),
    }.get(sort, Document.created_at.desc())
    rows = db.execute(stmt.order_by(order).limit(limit).offset(offset)).scalars().all()
    return {
        "items": [_serialize(d).model_dump() for d in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _get_readable(db: Session, principal: Principal, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or not can_read_document(db, principal.user, doc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if principal.is_api and principal.scoped_collection_ids:
        if not ({c.id for c in doc.collections} & set(principal.scoped_collection_ids)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    return _serialize(_get_readable(db, principal, document_id))


@router.get("/{document_id}/job", response_model=JobOut)
def get_document_job(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    _get_readable(db, principal, document_id)
    job = db.execute(
        select(IngestionJob).where(IngestionJob.document_id == document_id)
    ).scalars().first()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return _serialize_job(job)


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: str,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    doc = db.get(Document, document_id)
    if doc is None or not can_read_document(db, principal.user, doc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if not can_write_document(db, principal.user, doc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to modify this document")
    if payload.title is not None:
        doc.title = payload.title
    if payload.author is not None:
        doc.author = payload.author
    if payload.summary is not None:
        doc.summary = payload.summary
    if payload.collection_ids is not None:
        doc.collections = _resolve_collections(db, principal, payload.collection_ids)
    if payload.tags is not None:
        doc.tags = _resolve_tags(db, doc.organization_id, payload.tags)
    db.add(doc)
    db.commit()
    return _serialize(doc)


def _resolve_tags(db: Session, org_id: str, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for raw in names:
        name = raw.strip().lower()[:80]
        if not name:
            continue
        tag = db.execute(
            select(Tag).where(Tag.organization_id == org_id, Tag.name == name)
        ).scalars().first()
        if tag is None:
            tag = Tag(organization_id=org_id, name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)
    return tags


@router.post("/{document_id}/reprocess", response_model=JobOut)
def reprocess_document(
    document_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    doc = db.get(Document, document_id)
    if doc is None or not can_write_document(db, principal.user, doc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    job = db.execute(
        select(IngestionJob).where(IngestionJob.document_id == document_id)
    ).scalars().first()
    if job is None:
        job = IngestionJob(organization_id=doc.organization_id, document_id=doc.id)
    job.state = "PENDING"
    job.error = ""
    job.progress = 0.0
    doc.status = "pending"
    db.add_all([job, doc])
    db.commit()
    background.add_task(run_retry, document_id)
    return _serialize_job(job)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    doc = db.get(Document, document_id)
    if doc is None or not can_write_document(db, principal.user, doc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    org_id = doc.organization_id
    # Remove mirrored vectors first (DB cascade removes chunks + job).
    if is_qdrant_enabled():
        try:
            get_qdrant().delete_document(org_id, doc.id)
        except Exception:
            pass
    db.delete(doc)
    db.commit()
    audit.record(
        db,
        organization_id=org_id,
        action="document.delete",
        actor_id=principal.user.id,
        resource_type="document",
        resource_id=document_id,
    )
