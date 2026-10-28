from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Principal, client_ip, get_principal
from fastapi import Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.search import (
    AnswerRequest,
    AnswerResponse,
    EvidenceOut,
    ModelInfo,
    SearchRequest,
    SearchResponse,
)
from app.services import audit
from app.services.answer import generate_answer
from app.services.retrieval import RetrievalParams, retrieve

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _scoped_collection_ids(principal: Principal, requested: list[str]) -> list[str] | None:
    """Combine caller-requested collections with an API key's scope.

    Returns None for "all accessible" (web users with no explicit request).
    """
    if principal.is_api and principal.scoped_collection_ids:
        if requested:
            return [c for c in requested if c in principal.scoped_collection_ids]
        return list(principal.scoped_collection_ids)
    return requested or None


def _evidence_out(ev) -> EvidenceOut:
    d = ev.to_dict()
    return EvidenceOut(**d)


@router.post("/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    params = RetrievalParams(
        query=payload.query,
        collection_ids=_scoped_collection_ids(principal, payload.collection_ids),
        top_k=payload.top_k,
        min_score=payload.min_score,
        source_types=payload.source_types or None,
        categories=payload.categories or None,
        rerank=payload.rerank,
    )
    results = retrieve(db, principal.user, params)
    audit.record(
        db,
        organization_id=principal.user.organization_id,
        action="knowledge.search",
        actor_type=principal.auth_type,
        actor_id=principal.user.id,
        detail=f"q_len={len(payload.query)} results={len(results)}",
        ip_address=client_ip(request),
    )
    return SearchResponse(
        query=payload.query,
        count=len(results),
        results=[_evidence_out(e) for e in results],
    )


@router.post("/answer", response_model=AnswerResponse)
def answer(
    payload: AnswerRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    params = RetrievalParams(
        query=payload.query,
        collection_ids=_scoped_collection_ids(principal, payload.collection_ids),
        top_k=payload.top_k,
        min_score=payload.min_score,
        source_types=payload.source_types or None,
        categories=payload.categories or None,
        rerank=payload.rerank,
    )
    results = retrieve(db, principal.user, params)
    result = generate_answer(payload.query, results)
    audit.record(
        db,
        organization_id=principal.user.organization_id,
        action="knowledge.answer",
        actor_type=principal.auth_type,
        actor_id=principal.user.id,
        detail=f"evidence={len(results)} insufficient={result.insufficient_evidence}",
        ip_address=client_ip(request),
    )
    return AnswerResponse(
        query=payload.query,
        answer=result.answer,
        insufficient_evidence=result.insufficient_evidence,
        cited_labels=result.cited_labels,
        evidence=[_evidence_out(e) for e in result.evidence],
        model=ModelInfo(name=result.model_name, available=result.model_available),
        model_error=result.model_error,
    )
