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
| GET | `/voice/status` | any | Nyx TTS status (provider, availability) |
| POST | `/voice/tts` | any | Synthesize speech (WAV) for given text |
| GET | `/actions` | admin session | List available system actions (if enabled) |
| POST | `/actions/parse` | admin session | Parse an utterance into a structured command (no execution) |
| POST | `/actions/execute` | admin session | Execute a scoped action (nmap / app launch) |

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


## Chat & Conversations (Multi-turn)

SecBrain supports persistent, multi-turn conversations scoped to user collections.
Each conversation retains its message history, and subsequent queries include
recent turns as conversational context.

### List user conversations
``bash
curl -s localhost:8000/api/v1/conversations \
  -H "authorization: Bearer $TOKEN"
``

### Create a new conversation
``bash
curl -s -X POST localhost:8000/api/v1/conversations \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{\"title\":\"Log4j Mitigation Investigation\",\"collection_ids\":[]}'
``

### Post a message (with conversational memory)
``bash
curl -s -X POST localhost:8000/api/v1/conversations/{conv_id}/messages \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{\"message\":\"What are the mitigation steps for this vulnerability?\",\"top_k\":4}'
``

### Stream a response (Server-Sent Events)
``bash
curl -N -X POST localhost:8000/api/v1/conversations/{conv_id}/stream \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{\"message\":\"Summarize the key takeaways\"}'
``

### Retrieve message history
``bash
curl -s localhost:8000/api/v1/conversations/{conv_id}/messages \
  -H "authorization: Bearer $TOKEN"
``

### Delete a conversation
``bash
curl -s -X DELETE localhost:8000/api/v1/conversations/{conv_id} \
  -H "authorization: Bearer $TOKEN"
``

## Pagination & limits

`GET /documents` accepts `limit` (1–100), `offset`, `status`, `source_type`,
`collection_id`, `q`, `sort`. Responses include `total`, `limit`, `offset`.
`top_k` is bounded to 50. Errors use standard HTTP status codes with a
`{"detail": "..."}` body.

## Voice (Nyx TTS)

```bash
# Status (provider, whether the Piper voice model is available)
curl -s localhost:8000/api/v1/voice/status -H "authorization: Bearer $TOKEN"
# -> {"provider":"piper","available":true,"voice_name":"Nyx","model_path":"..."}

# Synthesize speech -> WAV audio (or 503 if the voice model isn't installed)
curl -s -X POST localhost:8000/api/v1/voice/tts \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"text":"Hello, I am Nyx."}' --output nyx.wav
```

A `503` means TTS is unavailable (e.g. voice model not downloaded); clients
should fall back to local/browser speech. Speech-to-text is handled client-side
by the browser, not by the API.

## System Actions (nmap / app launch)

Disabled unless `SECBRAIN_ACTIONS_ENABLED=true`. **Admin session only** (API
keys are rejected). Targets must be within an authorized scope (an active
Engagement or `SECBRAIN_ACTION_SCOPE_ALLOWLIST`); out-of-scope requests return
`403`. The executor uses argv lists (no shell) and fixed nmap profiles.

```bash
# What's available
curl -s localhost:8000/api/v1/actions -H "authorization: Bearer $TOKEN"
# -> {"enabled":true,"nmap_profiles":["ping","quick","service","top100"],
#     "allowed_apps":["firefox"],"scope_allowlist":["127.0.0.1/32"]}

# Parse a natural command into a structured action (NO execution)
curl -s -X POST localhost:8000/api/v1/actions/parse \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"text":"scan quick 127.0.0.1"}'
# -> {"action":"nmap","nmap":{"target":"127.0.0.1","profile":"quick","ports":null},
#     "confirm":"Run nmap 'quick' scan on 127.0.0.1?"}

# Execute (after user confirmation)
curl -s -X POST localhost:8000/api/v1/actions/execute \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"action":"nmap","nmap":{"target":"127.0.0.1","profile":"quick"}}'
# -> {"ok":true,"action":"nmap","detail":"profile=quick target=127.0.0.1 rc=0","output":"..."}

# Launch an allowlisted app
curl -s -X POST localhost:8000/api/v1/actions/execute \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"action":"launch_app","launch":{"name":"firefox"}}'
```

> The action layer is **never** invoked by the grounded-answer LLM or by content
> inside ingested documents — only by an authenticated admin's direct, structured
> request. See [THREAT_MODEL.md](THREAT_MODEL.md).

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
