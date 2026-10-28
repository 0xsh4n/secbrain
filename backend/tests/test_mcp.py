from __future__ import annotations

import json
import uuid

from app.core.security import hash_password
from app.mcp.server import handle_request
from app.mcp.tools import McpPrincipal, ToolError, call_tool
from app.models.collection import Collection
from app.models.organization import Organization, User
from app.services.samples import ingest_corpus


def _principal(db, scoped=None):
    org = Organization(name="M", slug="m-" + uuid.uuid4().hex[:6])
    db.add(org)
    db.flush()
    user = User(organization_id=org.id, email=f"m-{uuid.uuid4().hex[:6]}@x.test", hashed_password=hash_password("x"), role="admin")
    db.add(user)
    db.flush()
    coll = Collection(organization_id=org.id, owner_id=user.id, name="KB", slug="kb-" + uuid.uuid4().hex[:6], visibility="organization", category="vulnerability-research")
    db.add(coll)
    db.commit()
    ingest_corpus(db, user, coll)
    return McpPrincipal(user=user, scoped_collection_ids=scoped or []), coll


def test_mcp_search_tool(db):
    principal, _ = _principal(db)
    res = call_tool("search_security_knowledge", db, principal, {"query": "CVE-2021-44228 Log4j", "top_k": 3})
    assert res["count"] >= 1
    assert "log4" in res["results"][0]["title"].lower()


def test_mcp_list_collections(db):
    principal, coll = _principal(db)
    res = call_tool("list_accessible_collections", db, principal, {})
    assert any(c["id"] == coll.id for c in res["collections"])


def test_mcp_get_document_metadata_and_passages(db):
    principal, _ = _principal(db)
    search = call_tool("search_security_knowledge", db, principal, {"query": "JWT signature validation"})
    doc_id = search["results"][0]["document_id"]
    meta = call_tool("get_document_metadata", db, principal, {"document_id": doc_id})
    assert meta["id"] == doc_id
    passages = call_tool("get_source_passages", db, principal, {"document_id": doc_id})
    assert passages["passages"]
    assert all(p["chunk_id"] for p in passages["passages"])


def test_mcp_cross_tenant_denied(db):
    principal_a, _ = _principal(db)
    search = call_tool("search_security_knowledge", db, principal_a, {"query": "Log4j"})
    doc_id = search["results"][0]["document_id"]
    # A different principal (different org) cannot read doc A by id.
    principal_b, _ = _principal(db)
    try:
        call_tool("get_document_metadata", db, principal_b, {"document_id": doc_id})
        assert False, "expected ToolError"
    except ToolError:
        pass


def test_mcp_unknown_tool():
    import pytest

    with pytest.raises(ToolError):
        call_tool("delete_everything", None, None, {})


def test_mcp_jsonrpc_initialize_and_tools_list():
    init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "secbrain-mcp"
    tools = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert names == {
        "search_security_knowledge",
        "list_accessible_collections",
        "get_document_metadata",
        "get_source_passages",
    }
