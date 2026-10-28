"""MCP tool definitions and dispatch, built on the authorized service layer.

The tools are read-only and enforce exactly the same authorization as the REST
API: every call resolves to a concrete principal (an API key -> user + scoped
collections) and all retrieval/document access goes through the permission
layer. MCP is an integration surface, not a security boundary.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.document import Chunk, Document
from app.models.organization import User
from app.services.permissions import accessible_collection_ids, can_read_document
from app.services.retrieval import RetrievalParams, retrieve


@dataclass
class McpPrincipal:
    user: User
    scoped_collection_ids: list[str]


TOOL_DEFS = [
    {
        "name": "search_security_knowledge",
        "description": "Search the SecBrain cybersecurity knowledge base and return authorized evidence passages with source metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query."},
                "collection_ids": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_accessible_collections",
        "description": "List the knowledge collections the caller is authorized to read.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_document_metadata",
        "description": "Get metadata for a single document the caller is authorized to read.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
        },
    },
    {
        "name": "get_source_passages",
        "description": "Get the stored text passages (chunks) of a document the caller is authorized to read.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "required": ["document_id"],
        },
    },
]


class ToolError(Exception):
    pass


def _scoped(principal: McpPrincipal, requested: list[str] | None) -> list[str] | None:
    if principal.scoped_collection_ids:
        if requested:
            return [c for c in requested if c in principal.scoped_collection_ids]
        return list(principal.scoped_collection_ids)
    return requested or None


def _require_str(args: dict, key: str) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ToolError(f"Missing or invalid argument: {key}")
    return val.strip()


def search_security_knowledge(db: Session, principal: McpPrincipal, args: dict) -> dict:
    query = _require_str(args, "query")
    top_k = int(args.get("top_k", 8))
    top_k = max(1, min(top_k, 50))
    results = retrieve(
        db,
        principal.user,
        RetrievalParams(
            query=query,
            collection_ids=_scoped(principal, args.get("collection_ids")),
            top_k=top_k,
        ),
    )
    return {"query": query, "count": len(results), "results": [e.to_dict() for e in results]}


def list_accessible_collections(db: Session, principal: McpPrincipal, args: dict) -> dict:
    allowed = accessible_collection_ids(db, principal.user)
    if principal.scoped_collection_ids:
        allowed &= set(principal.scoped_collection_ids)
    rows = db.execute(select(Collection).where(Collection.id.in_(allowed or [""]))).scalars().all()
    return {
        "collections": [
            {"id": c.id, "name": c.name, "category": c.category, "visibility": c.visibility}
            for c in rows
        ]
    }


def _authorized_document(db: Session, principal: McpPrincipal, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or not can_read_document(db, principal.user, doc):
        raise ToolError("Document not found")
    if principal.scoped_collection_ids and not (
        {c.id for c in doc.collections} & set(principal.scoped_collection_ids)
    ):
        raise ToolError("Document not found")
    return doc


def get_document_metadata(db: Session, principal: McpPrincipal, args: dict) -> dict:
    doc = _authorized_document(db, principal, _require_str(args, "document_id"))
    return {
        "id": doc.id,
        "title": doc.title,
        "source_type": doc.source_type,
        "source_url": doc.source_url,
        "author": doc.author,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "embedding_version": doc.embedding_version,
        "collection_ids": [c.id for c in doc.collections],
        "tags": [t.name for t in doc.tags],
    }


def get_source_passages(db: Session, principal: McpPrincipal, args: dict) -> dict:
    doc = _authorized_document(db, principal, _require_str(args, "document_id"))
    limit = max(1, min(int(args.get("limit", 20)), 100))
    chunks = db.execute(
        select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.ordinal).limit(limit)
    ).scalars().all()
    return {
        "document_id": doc.id,
        "passages": [
            {
                "chunk_id": c.id,
                "ordinal": c.ordinal,
                "page_number": c.page_number,
                "section_heading": c.section_heading,
                "text": c.text,
            }
            for c in chunks
        ],
    }


_DISPATCH = {
    "search_security_knowledge": search_security_knowledge,
    "list_accessible_collections": list_accessible_collections,
    "get_document_metadata": get_document_metadata,
    "get_source_passages": get_source_passages,
}


def call_tool(name: str, db: Session, principal: McpPrincipal, args: dict) -> dict:
    fn = _DISPATCH.get(name)
    if fn is None:
        raise ToolError(f"Unknown tool: {name}")
    return fn(db, principal, args or {})
