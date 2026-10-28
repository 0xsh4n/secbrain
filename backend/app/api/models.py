from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_principal
from app.config import settings
from app.services.embeddings import get_embedding_provider
from app.services.llm import get_llm_provider

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/status")
def model_status(_principal=Depends(get_principal)) -> dict:
    """Model status page data. Never exposes API secrets."""
    llm = get_llm_provider()
    emb = get_embedding_provider()
    health = llm.health()
    return {
        "generation": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "available": health.available,
            "detail": health.detail,
            "context_tokens": settings.llm_context_tokens,
            "max_output_tokens": settings.llm_max_output_tokens,
            "outbound_disabled": settings.disable_outbound_llm,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        },
        "embedding": {
            "provider": settings.embedding_provider,
            "model": emb.model,
            "version": emb.version,
            "dim": emb.dim,
        },
        "vector_store": settings.vector_store,
    }
