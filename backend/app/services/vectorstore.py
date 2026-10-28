"""Vector store abstraction.

Two backends:

* ``memory`` (default): embeddings are persisted on chunk rows in the primary
  database; similarity is computed in-process with numpy. No extra service,
  survives restarts, and permission filtering happens naturally because the
  retrieval layer only scores chunks the caller is authorized to read.
* ``qdrant`` (optional): vectors are mirrored into Qdrant for scale. Security is
  still enforced in the service layer — the store is never the trust boundary.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from app.config import settings


@dataclass
class VectorPoint:
    chunk_id: str
    document_id: str
    organization_id: str
    collection_ids: list[str]
    vector: list[float]


@dataclass
class VectorHit:
    chunk_id: str
    score: float


def encode_vector(vec: list[float]) -> str:
    return json.dumps([round(float(x), 7) for x in vec])


def decode_vector(blob: str) -> list[float]:
    if not blob:
        return []
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return []


def cosine_scores(query: list[float], matrix: list[list[float]]) -> list[float]:
    """Cosine similarity of ``query`` against each row of ``matrix``.

    Vectors from providers are already L2-normalized, but we normalize again
    defensively so similarity stays in [-1, 1].
    """
    if not matrix:
        return []
    q = np.asarray(query, dtype=np.float32)
    m = np.asarray(matrix, dtype=np.float32)
    qn = np.linalg.norm(q)
    if qn == 0:
        return [0.0] * len(matrix)
    q = q / qn
    mn = np.linalg.norm(m, axis=1, keepdims=True)
    mn[mn == 0] = 1.0
    m = m / mn
    return (m @ q).tolist()


def is_qdrant_enabled() -> bool:
    return settings.vector_store.lower() == "qdrant"


class QdrantBackend:
    """Thin optional wrapper around qdrant-client. Imported lazily."""

    def __init__(self) -> None:
        from qdrant_client import QdrantClient

        self.collection = "secbrain_chunks"
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=30,
        )

    def ensure_collection(self, dim: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, points: list[VectorPoint]) -> None:
        from qdrant_client.models import PointStruct

        if not points:
            return
        self.ensure_collection(len(points[0].vector))
        self.client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=_uuid_point(p.chunk_id),
                    vector=p.vector,
                    payload={
                        "chunk_id": p.chunk_id,
                        "document_id": p.document_id,
                        "organization_id": p.organization_id,
                        "collection_ids": p.collection_ids,
                    },
                )
                for p in points
            ],
        )

    def delete_document(self, organization_id: str, document_id: str) -> None:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )

        self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="organization_id", match=MatchValue(value=organization_id)),
                        FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                    ]
                )
            ),
        )

    def search(
        self,
        organization_id: str,
        query_vec: list[float],
        allowed_collection_ids: list[str],
        limit: int,
    ) -> list[VectorHit]:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchAny,
            MatchValue,
        )

        must = [FieldCondition(key="organization_id", match=MatchValue(value=organization_id))]
        if allowed_collection_ids:
            must.append(
                FieldCondition(
                    key="collection_ids", match=MatchAny(any=allowed_collection_ids)
                )
            )
        res = self.client.search(
            collection_name=self.collection,
            query_vector=query_vec,
            query_filter=Filter(must=must),
            limit=limit,
            with_payload=True,
        )
        return [VectorHit(chunk_id=p.payload["chunk_id"], score=float(p.score)) for p in res]


def _uuid_point(chunk_id: str) -> str:
    # Qdrant point ids must be uuid or int; derive a stable uuid from chunk id.
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_OID, chunk_id))


_qdrant: QdrantBackend | None = None


def get_qdrant() -> QdrantBackend:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantBackend()
    return _qdrant
