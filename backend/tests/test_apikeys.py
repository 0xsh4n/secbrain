from __future__ import annotations

from sqlalchemy import select

from app.models.apikey import ApiKey


def _collection(client, headers):
    r = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": "KB", "visibility": "private", "category": "api-security"},
    )
    return r.json()["id"]


def test_api_key_lifecycle_and_usage(client, auth_headers, db):
    coll = _collection(client, auth_headers)
    # Create a key scoped to the collection.
    r = client.post(
        "/api/v1/apikeys",
        headers=auth_headers,
        json={"name": "integration", "scoped_collection_ids": [coll], "rate_limit_per_minute": 100},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    raw = created["api_key"]
    assert raw.startswith("sk_secbrain_")

    # Raw key is never stored; only a hash.
    stored = db.execute(select(ApiKey).where(ApiKey.id == created["id"])).scalars().first()
    assert stored.hashed_key != raw
    assert raw not in stored.hashed_key

    # Ingest a doc then use the API key to search.
    client.post(
        "/api/v1/documents/text",
        headers=auth_headers,
        json={"title": "d", "text": "JWT algorithm confusion RS256 HS256", "collection_ids": [coll]},
    )
    r = client.post(
        "/api/v1/knowledge/search",
        headers={"X-API-Key": raw},
        json={"query": "JWT algorithm confusion", "top_k": 5},
    )
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    # Admin-only operations must not be reachable with an API key.
    assert client.get("/api/v1/apikeys", headers={"X-API-Key": raw}).status_code == 403

    # Revoke -> key no longer works.
    assert client.delete(f"/api/v1/apikeys/{created['id']}", headers=auth_headers).status_code == 204
    r = client.post(
        "/api/v1/knowledge/search", headers={"X-API-Key": raw}, json={"query": "JWT"}
    )
    assert r.status_code == 401


def test_api_key_rate_limit(client, auth_headers):
    r = client.post(
        "/api/v1/apikeys",
        headers=auth_headers,
        json={"name": "rl", "rate_limit_per_minute": 3},
    )
    raw = r.json()["api_key"]
    statuses = [
        client.post("/api/v1/knowledge/search", headers={"X-API-Key": raw}, json={"query": "x"}).status_code
        for _ in range(5)
    ]
    assert 429 in statuses


def test_invalid_api_key_rejected(client):
    r = client.post(
        "/api/v1/knowledge/search",
        headers={"X-API-Key": "sk_secbrain_not_a_real_key"},
        json={"query": "x"},
    )
    assert r.status_code == 401
