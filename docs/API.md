# SecBrain API & Integration Guide

Base URL: `http://localhost:8000` · API prefix: `/api/v1` · Interactive docs:
`/docs` (Swagger) and `/api/v1/openapi.json`.

## Authentication

Two mechanisms resolve to the same authorization logic:

- **Bearer JWT** (`Authorization: Bearer <token>`) — interactive web users.
- **API key** (`X-API-Key: sk_secbrain_…`) — external AI applications.

API keys are scoped to collections, rate-limited, and logged. Admin/web-only
operations (document upload, API-key management, collection create/delete) reject
API-key auth and require a session.

### Get a session token

```bash
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@secbrain.local","password":"changeme-admin-123"}'
# -> { "access_token": "...", "token_type": "bearer", "expires_in_minutes": 720 }
```

### Create an API key (session only)

```bash
curl -s -X POST localhost:8000/api/v1/apikeys \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"my-agent","scoped_collection_ids":[],"rate_limit_per_minute":60}'
# -> { ..., "prefix":"sk_secbrain_ab12", "api_key":"sk_secbrain_...FULL..." }
```

The raw `api_key` is returned **once**. Store it securely; only a hash is kept.
Revoke with `DELETE /api/v1/apikeys/{id}`, rotate with
`POST /api/v1/apikeys/{id}/rotate`.

## Core endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | none | Liveness + component status |
| GET | `/models/status` | any | Model/provider status (no secrets) |
| POST | `/auth/register` | none | Create a workspace + admin |
| POST | `/auth/login` | none | Get a JWT |
| GET | `/auth/me` | session/key | Current principal |
| GET/POST | `/collections` | list: any / create: session | Collections |
| GET/PATCH/DELETE | `/collections/{id}` | mixed | Collection detail |
| POST | `/documents/text\|url\|upload` | session | Ingest |
| GET | `/documents` | any | List (pagination, filters, sort) |
| GET/PATCH/DELETE | `/documents/{id}` | mixed | Document detail / delete |
| POST | `/documents/{id}/reprocess` | session | Re-run ingestion |
| GET | `/documents/{id}/job` | any | Ingestion job status |
| POST | `/knowledge/search` | any | Hybrid retrieval |
| POST | `/knowledge/answer` | any | Grounded answer |
| POST/GET | `/conversations` … | session | Chat |
| GET | `/dashboard/stats`, `/dashboard/jobs` | session | Dashboard data |

## Search

```bash
curl -s -X POST localhost:8000/api/v1/knowledge/search \
  -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{
    "query": "How to prevent BOLA in APIs?",
    "collection_ids": [],
    "source_types": [],
    "categories": [],
    "top_k": 8,
    "rerank": false
  }'
```

Response:

```json
{
  "query": "How to prevent BOLA in APIs?",
  "count": 1,
  "results": [
    {
      "document_id": "…", "chunk_id": "…",
      "title": "API Access Controls and BOLA",
      "source_url": "", "source_type": "markdown",
      "text": "…passage…",
      "page_number": null, "section_heading": "Correct enforcement",
      "retrieval_method": "hybrid+identifier", "score": 1.23,
      "collection_ids": ["…"]
    }
  ]
}
```

Only authorized evidence passages are returned; full document contents are not
returned by default (fetch a document explicitly via `/documents/{id}`).

## Answer (grounded)

```bash
curl -s -X POST localhost:8000/api/v1/knowledge/answer \
  -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"query":"What is the fixed version for Log4Shell?","top_k":5}'
```

Response distinguishes a supported answer from insufficient evidence:

```json
{
  "query": "…",
  "answer": "…grounded answer citing [E1]…",
  "insufficient_evidence": false,
  "cited_labels": ["E1"],
  "evidence": [ { "chunk_id": "…", "title": "…", "...": "..." } ],
  "model": { "name": "ollama:qwen3:4b", "available": true },
  "model_error": ""
}
```

If no generation model is available, `model.available` is `false` and
`model_error` explains why — retrieval/evidence still work.

## Pagination & limits

`GET /documents` accepts `limit` (1–100), `offset`, `status`, `source_type`,
`collection_id`, `q`, `sort`. Responses include `total`, `limit`, `offset`.
`top_k` is bounded to 50. Errors use standard HTTP status codes with a
`{"detail": "..."}` body.

## MCP integration

SecBrain ships a read-only **Model Context Protocol** stdio server exposing:

- `search_security_knowledge(query, collection_ids?, top_k?)`
- `list_accessible_collections()`
- `get_document_metadata(document_id)`
- `get_source_passages(document_id, limit?)`

It enforces the same authorization as the REST API (via an API key) and has no
filesystem/shell/browser/network access of its own.

Run it:

```bash
cd backend && . .venv/bin/activate
SECBRAIN_MCP_API_KEY=sk_secbrain_... \
SECBRAIN_DATABASE_URL=sqlite:///./data/secbrain.db \
python -m app.mcp.server
```

Example MCP client config (stdio):

```json
{
  "mcpServers": {
    "secbrain": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/secbrain/backend",
      "env": {
        "SECBRAIN_MCP_API_KEY": "sk_secbrain_...",
        "SECBRAIN_DATABASE_URL": "postgresql+psycopg://secbrain:secbrain@localhost:5432/secbrain"
      }
    }
  }
}
```

The server speaks JSON-RPC 2.0 over stdio (newline-delimited). It implements
`initialize`, `tools/list`, and `tools/call`. Manual check:

```bash
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | SECBRAIN_MCP_API_KEY=sk_secbrain_... python -m app.mcp.server
```

> MCP is an integration surface, not a security boundary — permissions are
> enforced inside the service layer, so a misbehaving client still cannot exceed
> its API key's scope.
