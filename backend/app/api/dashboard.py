from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, require_session
from app.db import get_db
from app.models.audit import AuditLog
from app.models.collection import Collection
from app.models.document import Document, IngestionJob
from app.schemas.common import iso
from app.services.permissions import accessible_collection_ids

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(db: Session = Depends(get_db), principal: Principal = Depends(require_session)):
    user = principal.user
    org_id = user.organization_id

    total_docs = db.execute(
        select(func.count()).select_from(Document).where(Document.organization_id == org_id)
    ).scalar_one()

    status_counts = dict(
        db.execute(
            select(Document.status, func.count())
            .where(Document.organization_id == org_id)
            .group_by(Document.status)
        ).all()
    )

    job_counts = dict(
        db.execute(
            select(IngestionJob.state, func.count())
            .where(IngestionJob.organization_id == org_id)
            .group_by(IngestionJob.state)
        ).all()
    )

    collections = len(accessible_collection_ids(db, user))

    recent_docs = db.execute(
        select(Document)
        .where(Document.organization_id == org_id)
        .order_by(Document.created_at.desc())
        .limit(5)
    ).scalars().all()

    failed = db.execute(
        select(IngestionJob)
        .where(IngestionJob.organization_id == org_id, IngestionJob.state == "FAILED")
        .order_by(IngestionJob.updated_at.desc())
        .limit(5)
    ).scalars().all()

    recent_searches = db.execute(
        select(AuditLog)
        .where(
            AuditLog.organization_id == org_id,
            AuditLog.action.in_(["knowledge.search", "knowledge.answer"]),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(5)
    ).scalars().all()

    total_chunks = db.execute(
        select(func.coalesce(func.sum(Document.chunk_count), 0)).where(
            Document.organization_id == org_id
        )
    ).scalar_one()

    return {
        "total_documents": total_docs,
        "documents_by_status": status_counts,
        "collections": collections,
        "jobs_by_state": job_counts,
        "total_chunks": int(total_chunks or 0),
        "recent_documents": [
            {"id": d.id, "title": d.title, "status": d.status, "created_at": iso(d.created_at)}
            for d in recent_docs
        ],
        "failed_jobs": [
            {"document_id": j.document_id, "error": j.error[:200], "updated_at": iso(j.updated_at)}
            for j in failed
        ],
        "recent_searches": [
            {"action": a.action, "detail": a.detail, "created_at": iso(a.created_at)}
            for a in recent_searches
        ],
    }


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db), principal: Principal = Depends(require_session)):
    rows = db.execute(
        select(IngestionJob)
        .where(IngestionJob.organization_id == principal.user.organization_id)
        .order_by(IngestionJob.updated_at.desc())
        .limit(100)
    ).scalars().all()
    return [
        {
            "id": j.id,
            "document_id": j.document_id,
            "state": j.state,
            "progress": j.progress,
            "detail": j.detail,
            "error": j.error,
            "attempts": j.attempts,
            "updated_at": iso(j.updated_at),
        }
        for j in rows
    ]
