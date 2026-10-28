from __future__ import annotations

import json
import uuid
import zipfile
from datetime import timedelta
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit, urlunsplit

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
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal, require_session
from app.config import settings
from app.core.slugs import slugify
from app.core.taxonomy import SECURITY_CATEGORIES
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
from app.services.storage import get_storage
from app.services.permissions import (
    accessible_collection_ids,
    can_read_collection,
    can_read_document,
    can_write_document,
)
from app.services.tasks import run_ingestion, run_retry
from app.services.vectorstore import get_qdrant, is_qdrant_enabled

router = APIRouter(prefix="/documents", tags=["documents"])

_BACKUP_VERSION = 2
_BACKUP_MAX_BYTES = 512 * 1024 * 1024
_BACKUP_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
_BACKUP_MAX_FILES = 5000
_SOURCE_EXTENSIONS = {"pdf": "pdf", "txt": "txt", "markdown": "md", "html": "html", "docx": "docx"}


def _backup_source_url(value: str) -> str:
    """Keep citation provenance without exporting URL credentials or query tokens."""
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except (ValueError, TypeError):
        return ""


def _accessible_documents(db: Session, principal: Principal) -> list[Document]:
    user = principal.user
    accessible = accessible_collection_ids(db, user)
    if principal.is_api and principal.scoped_collection_ids:
        accessible &= set(principal.scoped_collection_ids)
    stmt = select(Document).where(Document.organization_id == user.organization_id)
    if principal.is_api or not user.is_admin:
        coll_docs = select(document_collections.c.document_id).where(
            document_collections.c.collection_id.in_(accessible or [""])
        )
        from sqlalchemy import or_

        clause = Document.id.in_(coll_docs)
        if not principal.is_api:
            clause = or_(Document.owner_id == user.id, clause)
        stmt = stmt.where(clause)
    return db.execute(stmt.order_by(Document.created_at.asc())).scalars().unique().all()

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


@router.get("/backup/export")
def export_library_backup(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    """Export accessible knowledge documents as a portable, re-indexable ZIP."""
    user = principal.user
    archive = SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b")
    manifest = {"format": "secbrain-library", "version": _BACKUP_VERSION, "documents": []}

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for index, doc in enumerate(_accessible_documents(db, principal), start=1):
            # Back up the ingested knowledge representation, never original PDFs/files.
            text = (doc.extracted_text or "").strip()
            if not text:
                continue
            raw = text.encode("utf-8")
            archive_path = f"knowledge/{index:06d}.txt"
            bundle.writestr(archive_path, raw)
            allowed_collections = [
                c for c in doc.collections if can_read_collection(db, user, c)
            ]
            manifest["documents"].append(
                {
                    "path": archive_path,
                    "content_kind": "extracted_text",
                    "title": doc.title or f"Document {index}",
                    "source_type": doc.source_type,
                    "source_url": _backup_source_url(doc.source_url),
                    "author": doc.author,
                    "summary": doc.summary,
                    "mime_type": doc.mime_type,
                    "content_hash": doc.content_hash,
                    "tags": [tag.name for tag in doc.tags],
                    "collections": [
                        {"name": c.name, "description": c.description, "category": c.category}
                        for c in allowed_collections
                    ],
                }
            )
        manifest["created_at"] = utcnow().isoformat()
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    archive.seek(0)

    def stream_archive():
        try:
            while chunk := archive.read(1024 * 1024):
                yield chunk
        finally:
            archive.close()

    return StreamingResponse(
        stream_archive(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="secbrain-library-backup.zip"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/backup/import", status_code=status.HTTP_202_ACCEPTED)
async def import_library_backup(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    """Restore documents from a SecBrain backup, then rebuild their indexes."""
    upload = file.file
    upload.seek(0, 2)
    archive_size = upload.tell()
    upload.seek(0)
    if archive_size <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a non-empty ZIP backup")
    if archive_size > _BACKUP_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Backup ZIP exceeds the 512 MB limit")

    try:
        bundle = zipfile.ZipFile(upload)
    except (zipfile.BadZipFile, OSError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This file is not a valid ZIP backup")

    with bundle:
        infos = bundle.infolist()
        if len(infos) > _BACKUP_MAX_FILES + 1:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Backup contains too many files")
        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > _BACKUP_MAX_UNCOMPRESSED_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Uncompressed backup exceeds the 2 GB limit")
        for info in infos:
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or "\\" in info.filename:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Backup contains an unsafe file path")

        try:
            manifest = json.loads(bundle.read("manifest.json"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Backup manifest is missing or invalid")
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "secbrain-library"
            or manifest.get("version") not in {1, _BACKUP_VERSION}
            or not isinstance(manifest.get("documents"), list)
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported SecBrain backup format")
        if len(manifest["documents"]) > _BACKUP_MAX_FILES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Backup contains too many documents")

        user = principal.user
        storage = get_storage()
        accessible_hashes = {
            doc.content_hash
            for doc in _accessible_documents(db, principal)
            if doc.content_hash and not doc.is_duplicate
        }
        collection_map: dict[tuple[str, str], Collection] = {}
        imported = 0
        skipped = 0

        for entry in manifest["documents"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                skipped += 1
                continue
            member = PurePosixPath(entry["path"])
            if member.is_absolute() or ".." in member.parts or entry["path"] not in bundle.namelist():
                skipped += 1
                continue
            info = bundle.getinfo(entry["path"])
            if info.file_size > settings.max_upload_bytes:
                skipped += 1
                continue
            try:
                raw = bundle.read(info)
            except (zipfile.BadZipFile, OSError):
                skipped += 1
                continue
            if not raw:
                skipped += 1
                continue

            content_hash = str(entry.get("content_hash") or "")
            if content_hash and content_hash in accessible_hashes:
                skipped += 1
                continue

            title = str(entry.get("title") or "Imported document")[:500]
            content_kind = entry.get("content_kind")
            source_url = _backup_source_url(str(entry.get("source_url") or ""))
            storage_key = ""
            inline_text = ""
            source_type = "text"
            extension = member.suffix.lstrip(".").lower()
            if content_kind == "file" and extension in _SOURCE_EXTENSIONS.values():
                source_type = next(
                    (kind for kind, ext in _SOURCE_EXTENSIONS.items() if ext == extension),
                    "text",
                )
                storage_key = f"{user.organization_id}/{uuid.uuid4().hex}.{extension}"
                storage.save(storage_key, raw)
            else:
                try:
                    inline_text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue

            collection_ids: list[str] = []
            collection_entries = entry.get("collections", [])
            if isinstance(collection_entries, list):
                for collection_entry in collection_entries[:50]:
                    if not isinstance(collection_entry, dict):
                        continue
                    name = str(collection_entry.get("name") or "Imported library")[:200].strip()
                    if not name:
                        continue
                    category = str(collection_entry.get("category") or "")[:60]
                    if category not in SECURITY_CATEGORIES:
                        category = ""
                    key = (name, category)
                    collection = collection_map.get(key)
                    if collection is None:
                        slug = slugify(name, "imported-library")[:120]
                        existing = db.execute(
                            select(Collection).where(
                                Collection.organization_id == user.organization_id,
                                Collection.slug == slug,
                            )
                        ).scalars().first()
                        if (
                            existing
                            and existing.name == name
                            and existing.owner_id == user.id
                            and existing.visibility == "private"
                        ):
                            collection = existing
                        else:
                            while existing:
                                slug = f"{slug[:110]}-{uuid.uuid4().hex[:8]}"
                                existing = db.execute(
                                    select(Collection).where(
                                        Collection.organization_id == user.organization_id,
                                        Collection.slug == slug,
                                    )
                                ).scalars().first()
                            collection = Collection(
                                organization_id=user.organization_id,
                                owner_id=user.id,
                                name=name,
                                slug=slug,
                                description=str(collection_entry.get("description") or "")[:1000],
                                category=category,
                                visibility="private",
                            )
                            db.add(collection)
                            db.flush()
                        collection_map[key] = collection
                    collection_ids.append(collection.id)

            doc = _create_and_queue(
                db,
                principal,
                background,
                title=title,
                source_type=source_type,
                source_url=source_url,
                storage_key=storage_key,
                mime_type=str(entry.get("mime_type") or "")[:120],
                inline_text=inline_text,
                collection_ids=collection_ids,
                byte_size=len(raw),
            )
            doc.author = str(entry.get("author") or "")[:300]
            doc.summary = str(entry.get("summary") or "")[:20000]
            doc.content_hash = content_hash
            tags = entry.get("tags", [])
            if isinstance(tags, list):
                doc.tags = _resolve_tags(db, user.organization_id, [str(tag) for tag in tags[:100]])
            db.add(doc)
            imported += 1
            if content_hash:
                accessible_hashes.add(content_hash)

        db.commit()
        return {"imported": imported, "skipped": skipped, "message": "Imported documents are queued for re-indexing."}


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
