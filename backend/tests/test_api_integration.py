from __future__ import annotations


def _create_collection(client, headers, name="Web"):
    r = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": name, "visibility": "private", "category": "web-application-security"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ingest_text(client, headers, coll_id, text, title="T"):
    r = client.post(
        "/api/v1/documents/text",
        headers=headers,
        json={"title": title, "text": text, "collection_ids": [coll_id]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_full_knowledge_flow(client, auth_headers):
    coll = _create_collection(client, auth_headers)
    doc_id = _ingest_text(
        client,
        auth_headers,
        coll,
        "Broken object level authorization (BOLA) is the top API risk. "
        "Check object ownership on every request. CVE-2021-44228 is Log4Shell.",
        title="API Security Notes",
    )
    # Background ingestion runs synchronously under TestClient -> indexed.
    doc = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers).json()
    assert doc["status"] == "indexed", doc
    assert doc["chunk_count"] >= 1

    # Search returns evidence with real metadata.
    r = client.post(
        "/api/v1/knowledge/search",
        headers=auth_headers,
        json={"query": "How to prevent BOLA in APIs?", "top_k": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    ev = body["results"][0]
    assert ev["document_id"] == doc_id
    assert ev["chunk_id"]

    # Answer endpoint returns grounded answer with citations to real evidence.
    r = client.post(
        "/api/v1/knowledge/answer",
        headers=auth_headers,
        json={"query": "How to prevent BOLA in APIs?", "top_k": 5},
    )
    assert r.status_code == 200
    ans = r.json()
    assert ans["evidence"]
    assert all(e["chunk_id"] for e in ans["evidence"])

    # Delete removes from subsequent searches.
    assert client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers).status_code == 204
    r = client.post(
        "/api/v1/knowledge/search",
        headers=auth_headers,
        json={"query": "How to prevent BOLA in APIs?", "top_k": 5},
    )
    assert r.json()["count"] == 0


def test_cross_tenant_document_access_denied(client, auth_headers, other_headers):
    coll = _create_collection(client, auth_headers)
    doc_id = _ingest_text(client, auth_headers, coll, "secret org A content about kerberos")
    # Mallory (other org) cannot read Alice's document by id.
    r = client.get(f"/api/v1/documents/{doc_id}", headers=other_headers)
    assert r.status_code == 404
    # Nor via search.
    r = client.post("/api/v1/knowledge/search", headers=other_headers, json={"query": "kerberos"})
    assert r.json()["count"] == 0


def test_requires_auth(client):
    assert client.get("/api/v1/documents").status_code == 401
    assert client.post("/api/v1/knowledge/search", json={"query": "x"}).status_code == 401


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_security_headers_present(client):
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
