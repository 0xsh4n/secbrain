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
import heapq
from collections import defaultdict
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


_RETRIEVAL_BATCH_SIZE = 256


def _iter_chunk_batches(db: Session, statement):
    result = db.execute(statement.execution_options(yield_per=_RETRIEVAL_BATCH_SIZE))
    try:
        yield from result.partitions(_RETRIEVAL_BATCH_SIZE)
    finally:
        result.close()


def _batch_scores(rows, query_vec: list[float]) -> list[float]:
    matrix = [decode_vector(row.embedding) for row in rows]
    return cosine_scores(query_vec, matrix)


def _lexical_score(terms: set[str], idf: dict[str, float], total_weight: float) -> float:
    if total_weight <= 0:
        return 0.0
    return sum(idf[term] for term in terms if term in idf) / total_weight


def retrieve(db: Session, user: User, params: RetrievalParams) -> list[Evidence]:
    """Scan the corpus in small batches and retain only final candidates."""
    doc_ids = _resolve_scope_document_ids(db, user, params)
    if not doc_ids:
        return []

    provider = get_embedding_provider()
    query_vec = provider.embed_one(params.query)
    query_terms = _content_terms(params.query)
    identifiers = set(all_identifiers(params.query))
    candidate_limit = max(params.top_k * settings.retrieval_candidate_multiplier, params.top_k)
    statement = (
        select(
            Chunk.id.label("chunk_id"), Chunk.document_id.label("document_id"),
            Chunk.embedding.label("embedding"), Chunk.text.label("text"),
            Chunk.page_number.label("page_number"), Chunk.section_heading.label("section_heading"),
            Document.title.label("title"), Document.source_url.label("source_url"),
            Document.source_type.label("source_type"),
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.document_id.in_(doc_ids), Chunk.embedding_model == provider.version)
        .order_by(Document.created_at.desc(), Chunk.ordinal.asc())
        .limit(max(100, settings.retrieval_max_scan_chunks))
    )

    # Pass 1: corpus-wide term frequencies, with only one batch of text resident.
    document_frequency = dict.fromkeys(query_terms, 0)
    row_count = 0
    for batch in _iter_chunk_batches(db, statement):
        for row in batch:
            row_count += 1
            for term in _content_terms(row.text) & query_terms:
                document_frequency[term] += 1
    if row_count == 0:
        return []
    idf = {term: math.log((row_count + 1) / (frequency + 1)) + 1.0 for term, frequency in document_frequency.items()}
    total_idf = sum(idf.values())

    def scored_batches():
        for batch in _iter_chunk_batches(db, statement):
            vector_scores = _batch_scores(batch, query_vec)
            for row, vector_score in zip(batch, vector_scores):
                terms = _content_terms(row.text)
                lexical_score = _lexical_score(terms, idf, total_idf)
                has_identifier = any(identifier.lower() in row.text.lower() for identifier in identifiers)
                qualifies = has_identifier or lexical_score >= settings.retrieval_min_lexical
                if not settings.retrieval_require_lexical_grounding:
                    qualifies = qualifies or vector_score >= settings.retrieval_min_cosine
                if qualifies:
                    yield row, vector_score, lexical_score, has_identifier

    # Pass 2: corpus-wide score ranges for the existing min-max fusion.
    vector_min = lexical_min = float("inf")
    vector_max = lexical_max = float("-inf")
    qualified_count = 0
    for _row, vector_score, lexical_score, _identifier in scored_batches():
        vector_min, vector_max = min(vector_min, vector_score), max(vector_max, vector_score)
        lexical_min, lexical_max = min(lexical_min, lexical_score), max(lexical_max, lexical_score)
        qualified_count += 1
    if qualified_count == 0:
        return []

    # Pass 3: stream scores into a bounded top-candidate heap.
    heap: list[tuple[float, int, float, str, object]] = []
    sequence = 0
    for row, vector_score, lexical_score, has_identifier in scored_batches():
        normalized_vector = 0.0 if vector_max - vector_min < 1e-9 else (vector_score - vector_min) / (vector_max - vector_min)
        normalized_lexical = 0.0 if lexical_max - lexical_min < 1e-9 else (lexical_score - lexical_min) / (lexical_max - lexical_min)
        fused = 0.55 * normalized_vector + 0.45 * normalized_lexical + (0.25 if has_identifier else 0.0)
        if fused < params.min_score:
            continue
        if has_identifier:
            method = "hybrid+identifier"
        elif normalized_lexical > 0 and normalized_vector > 0:
            method = "hybrid"
        elif normalized_lexical > 0:
            method = "keyword"
        else:
            method = "vector"
        rank = fused
        if params.rerank:
            if query_terms & _content_terms(row.section_heading or ""):
                rank += 0.1
            if any(identifier.lower() in row.text.lower() for identifier in identifiers):
                rank += 0.2
        entry = (rank, sequence, fused, method, row)
        sequence += 1
        if len(heap) < candidate_limit:
            heapq.heappush(heap, entry)
        elif entry[:2] > heap[0][:2]:
            heapq.heapreplace(heap, entry)

    selected = sorted(heap, key=lambda entry: (entry[0], entry[1]), reverse=True)
    selected = selected[:params.top_k]
    document_ids = {entry[4].document_id for entry in selected}
    memberships: dict[str, list[str]] = defaultdict(list)
    if document_ids:
        from app.models.collection import document_collections
        links = db.execute(
            select(document_collections.c.document_id, document_collections.c.collection_id)
            .where(document_collections.c.document_id.in_(document_ids))
        ).all()
        for document_id, collection_id in links:
            memberships[document_id].append(collection_id)

    return [
        Evidence(
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            title=row.title or "(untitled)",
            source_url=row.source_url,
            source_type=row.source_type,
            text=row.text,
            page_number=row.page_number,
            section_heading=row.section_heading or "",
            retrieval_method=method,
            score=fused,
            collection_ids=memberships.get(row.document_id, []),
        )
        for _rank, _seq, fused, method, row in selected
    ]


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
