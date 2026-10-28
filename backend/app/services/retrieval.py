"""Hybrid retrieval engine.

Combines semantic vector similarity, keyword/full-text scoring, metadata
filtering, exact security-identifier boosting and optional lexical reranking.
Authorization is applied BEFORE any scoring: only chunks the caller may read
enter the candidate set, so evidence can never leak across tenants/collections.

Vector similarity is computed from embeddings stored on chunk rows (works on
SQLite and Postgres, no external service). Qdrant, when enabled, is kept in
sync for external/large-scale use but is not required for correctness.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# Minimal English stopword list for lexical grounding (keeps distinctive terms).
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "are",
    "be", "with", "how", "do", "i", "what", "which", "that", "this", "it", "as",
    "at", "by", "from", "should", "can", "my", "me", "when", "where", "why",
    "was", "were", "has", "have", "if", "but", "not", "no", "so", "into", "over",
    "about", "there", "would", "you", "your", "we", "they", "them",
}

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.taxonomy import all_identifiers
from app.models.collection import Collection, document_collections
from app.models.document import Chunk, Document
from app.models.organization import User
from app.services.embeddings import get_embedding_provider
from app.services.permissions import accessible_collection_ids
from app.services.vectorstore import cosine_scores, decode_vector


@dataclass
class Evidence:
    document_id: str
    chunk_id: str
    title: str
    source_url: str
    source_type: str
    text: str
    page_number: int | None
    section_heading: str
    retrieval_method: str
    score: float
    collection_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "text": self.text,
            "page_number": self.page_number,
            "section_heading": self.section_heading,
            "retrieval_method": self.retrieval_method,
            "score": round(self.score, 5),
            "collection_ids": self.collection_ids,
        }


@dataclass
class RetrievalParams:
    query: str
    collection_ids: list[str] | None = None
    top_k: int = settings.retrieval_top_k
    min_score: float = settings.retrieval_min_score
    source_types: list[str] | None = None
    categories: list[str] | None = None
    rerank: bool = False


_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-\._/]*")


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def decompose_query(query: str) -> list[str]:
    """Light query decomposition: pull out exact identifiers as sub-queries."""
    return all_identifiers(query)


def _resolve_scope_document_ids(
    db: Session, user: User, params: RetrievalParams
) -> list[str]:
    accessible = accessible_collection_ids(db, user)
    requested = params.collection_ids
    if requested:
        scope_collections = [c for c in requested if c in accessible]
        if not scope_collections:
            return []
    else:
        scope_collections = list(accessible)

    base = select(Document.id).where(
        Document.organization_id == user.organization_id,
        Document.status == "indexed",
        Document.is_duplicate.is_(False),
    )

    if params.source_types:
        base = base.where(Document.source_type.in_(params.source_types))

    if requested:
        # Restricted to the requested (accessible) collections.
        base = base.where(
            Document.id.in_(
                select(document_collections.c.document_id).where(
                    document_collections.c.collection_id.in_(scope_collections)
                )
            )
        )
    else:
        if not user.is_admin:
            # Owned docs (even if in no collection) OR docs in accessible collections.
            coll_docs = select(document_collections.c.document_id).where(
                document_collections.c.collection_id.in_(scope_collections)
            )
            base = base.where(or_(Document.owner_id == user.id, Document.id.in_(coll_docs)))

    if params.categories:
        cat_colls = select(Collection.id).where(
            Collection.organization_id == user.organization_id,
            Collection.category.in_(params.categories),
        )
        cat_docs = select(document_collections.c.document_id).where(
            document_collections.c.collection_id.in_(cat_colls)
        )
        base = base.where(Document.id.in_(cat_docs))

    return list(db.execute(base).scalars().all())


def _singularize(token: str) -> str:
    """Very light plural normalization so e.g. 'apis'<->'api', 'urls'<->'url'
    match. Not a full stemmer; just collapses a common source of lexical
    mismatch between queries and documents."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _content_terms(text: str) -> set[str]:
    return {
        _singularize(t)
        for t in _tokens(text)
        if t not in _STOPWORDS and len(t) > 1
    }


def _idf_overlap(query_terms: set[str], candidate_terms: list[set[str]]) -> list[float]:
    """IDF-weighted fraction of the query's informational mass each candidate
    matches. Terms absent from the whole corpus still count toward the query's
    total weight, so a query whose distinctive terms appear nowhere scores low
    everywhere (-> abstention)."""
    if not query_terms:
        return [0.0] * len(candidate_terms)
    n = len(candidate_terms)
    df = {t: sum(1 for ts in candidate_terms if t in ts) for t in query_terms}
    idf = {t: math.log((n + 1) / (df[t] + 1)) + 1.0 for t in query_terms}
    total = sum(idf.values()) or 1.0
    out = []
    for ts in candidate_terms:
        matched = sum(idf[t] for t in query_terms if t in ts)
        out.append(matched / total)
    return out


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def retrieve(db: Session, user: User, params: RetrievalParams) -> list[Evidence]:
    doc_ids = _resolve_scope_document_ids(db, user, params)
    if not doc_ids:
        return []

    provider = get_embedding_provider()
    # Over-fetch candidate chunks (bounded) before fusion.
    candidate_limit = max(params.top_k * settings.retrieval_candidate_multiplier, params.top_k)

    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.document_id.in_(doc_ids))
        # Only score chunks embedded in the CURRENT embedding space.
        .where(Chunk.embedding_model == provider.version)
    ).all()
    if not rows:
        return []

    query_vec = provider.embed_one(params.query)
    matrix = [decode_vector(chunk.embedding) for chunk, _ in rows]
    vec_scores = cosine_scores(query_vec, matrix)

    query_terms = _content_terms(params.query)
    identifiers = set(all_identifiers(params.query))
    candidate_terms = [_content_terms(chunk.text) for chunk, _ in rows]
    lex_scores = _idf_overlap(query_terms, candidate_terms)
    has_identifier = [
        any(ident.lower() in chunk.text.lower() for ident in identifiers)
        for chunk, _ in rows
    ]

    # Relevance gate -> controls abstention on unsupported questions.
    qualifying: list[int] = []
    for i in range(len(rows)):
        ok = has_identifier[i] or lex_scores[i] >= settings.retrieval_min_lexical
        if not settings.retrieval_require_lexical_grounding:
            ok = ok or vec_scores[i] >= settings.retrieval_min_cosine
        if ok:
            qualifying.append(i)
    if not qualifying:
        return []

    nv_all = _minmax([vec_scores[i] for i in qualifying])
    nl_all = _minmax([lex_scores[i] for i in qualifying])

    scored: list[tuple[float, str, Chunk, Document]] = []
    for pos, i in enumerate(qualifying):
        chunk, doc = rows[i]
        nv_i, nl_i = nv_all[pos], nl_all[pos]
        id_boost = 0.25 if has_identifier[i] else 0.0
        fused = 0.55 * nv_i + 0.45 * nl_i + id_boost
        if has_identifier[i]:
            method = "hybrid+identifier"
        elif nl_i > 0 and nv_i > 0:
            method = "hybrid"
        elif nl_i > 0:
            method = "keyword"
        else:
            method = "vector"
        scored.append((fused, method, chunk, doc))

    scored.sort(key=lambda t: t[0], reverse=True)

    if params.rerank:
        scored = _lexical_rerank(query_terms, identifiers, scored)

    results: list[Evidence] = []
    for fused, method, chunk, doc in scored[: candidate_limit]:
        if fused < params.min_score:
            continue
        results.append(
            Evidence(
                document_id=doc.id,
                chunk_id=chunk.id,
                title=doc.title or "(untitled)",
                source_url=doc.source_url,
                source_type=doc.source_type,
                text=chunk.text,
                page_number=chunk.page_number,
                section_heading=chunk.section_heading,
                retrieval_method=method,
                score=fused,
                collection_ids=[c.id for c in doc.collections],
            )
        )
        if len(results) >= params.top_k:
            break
    return results


def _lexical_rerank(
    query_tokens: set[str],
    identifiers: set[str],
    scored: list[tuple[float, str, Chunk, Document]],
) -> list[tuple[float, str, Chunk, Document]]:
    """Optional, cheap rerank: promote chunks whose heading matches the query
    or that contain exact identifiers. No external model is used."""

    def key(item):
        fused, _method, chunk, _doc = item
        heading_tokens = set(_tokens(chunk.section_heading))
        heading_bonus = 0.1 if (query_tokens & heading_tokens) else 0.0
        id_bonus = 0.2 if any(i.lower() in chunk.text.lower() for i in identifiers) else 0.0
        return fused + heading_bonus + id_bonus

    return sorted(scored, key=key, reverse=True)
