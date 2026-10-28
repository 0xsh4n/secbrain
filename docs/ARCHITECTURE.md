# SecBrain Architecture

## Overview

SecBrain is a modular RAG knowledge platform with clearly separated services. It
is built so the knowledge layer is the durable asset and the LLM is a replaceable
component.

```
                +-------------------+
                |   Next.js Web UI  |  (TS + Tailwind, dark dashboard)
                +---------+---------+
                          | REST (JWT)
                          v
+-----------+     +-------------------+     +------------------+
| MCP client| --> |   FastAPI backend | <-- | External AI apps |
+-----------+ MCP |  (API key / JWT)  | REST+API key +------------------+
                  +----+---------+----+
                       |         |
          +------------+         +-------------+
          v                                    v
  +---------------+                    +------------------+
  |  PostgreSQL   |  metadata,         |  Vector store    |
  |  (or SQLite)  |  docs, chunks,     |  memory (numpy)  |
  |               |  embeddings,       |  or Qdrant       |
  |               |  api keys, audit   |                  |
  +---------------+                    +------------------+
          ^                                    ^
          |          Provider abstraction      |
          +----+-------------------------+------+
               v                         v
        +--------------+          +---------------+
        | Embeddings   |          |  Generation   |
        | fake/ollama/ |          | fake/ollama/  |
        | openai       |          | openai        |
        +--------------+          +---------------+
```

## Backend layering

```
app/
  config.py              env-driven settings (model/provider/infra choices)
  db.py                  SQLAlchemy engine/session (SQLite or Postgres)
  core/                  security (hashing/JWT/API keys), taxonomy, slugs
  models/                ORM: org, user, collection, document, chunk, job,
                         api key, conversation, audit, engagement
  schemas/               Pydantic request/response models
  services/              business logic (no FastAPI imports):
      storage            raw-bytes storage abstraction (local FS -> S3-ready)
      extraction         PDF/TXT/MD/HTML/DOCX -> normalized text + page segments
      chunking           heading-aware, size-bounded chunking with overlap
      embeddings         provider abstraction (fake/ollama/openai), versioned
      llm                generation provider abstraction + health
      vectorstore        numpy cosine + optional Qdrant backend
      url_fetcher        SSRF-resistant outbound fetcher
      permissions        collection access resolution + document read/write checks
      ingestion          pipeline orchestration + state machine
      retrieval          hybrid retrieval + evidence objects
      answer             grounded answer generation (injection-safe)
      metadata           heuristic security metadata suggestion
      samples            synthetic corpus seeding (also the eval corpus)
      audit, tasks
  api/                   FastAPI routers (thin; delegate to services)
  mcp/                   MCP stdio adapter over the service layer
  cli.py                 init-db / bootstrap / seed-samples
```

The **services layer contains all logic and is framework-agnostic**, so the REST
API, the MCP adapter, the CLI, and the eval harness all reuse it and all get the
same authorization enforcement.

## Data model (key tables)

- `organizations` — tenant boundary. All knowledge is isolated per org.
- `users` — belong to an org; role `admin`/`member`.
- `collections` — org-scoped; `visibility` = `private` | `organization`; carry a
  security `category`. `collection_members` grant explicit access to private
  collections.
- `documents` — org + owner scoped; many-to-many with collections and tags;
  hold extracted text, content hash, status, embedding version, duplicate flags.
- `chunks` — per-document passages with embedding (stored as JSON), page number,
  section heading, and embedding-model version.
- `ingestion_jobs` — state machine record (progress, detail, error, attempts).
- `api_keys` — hashed key, prefix, collection scope, rate limit, expiry, usage.
- `conversations` / `messages` — chat history with citations.
- `audit_logs` — minimal, non-sensitive action records.
- `engagements` — conceptual authorization model for *future* active testing
  (fails closed; no active testing implemented in this release).

## Ingestion pipeline

State machine: `PENDING → FETCHING → EXTRACTING → INDEXING → COMPLETED`, with
`FAILED` (recorded, retryable) and `CANCELLED`.

1. Validate input → create document record → check permissions/collection access.
2. Fetch (SSRF-safe) or load uploaded/pasted bytes.
3. Extract + normalize (preserving headings, code blocks, tables, page segments).
4. Compute content hash; detect duplicates within the org.
5. Suggest security metadata (heuristic; identifiers, category hints).
6. Chunk → embed → persist chunks → (optionally) mirror vectors to Qdrant.
7. Mark `indexed` only if extraction **and** embedding/indexing succeeded.

A document is never silently marked indexed when a stage fails; errors are
recorded on both the job and the document and the job is retryable.

## Retrieval

For each query, over the caller's authorized chunk set:

1. **Authorization first** — only chunks in collections the caller may read (and
   within the API key's scope) enter the candidate set.
2. **Vector similarity** — cosine over embeddings in the current embedding space
   (embedding versions are tracked so incompatible spaces are never mixed).
3. **Lexical grounding** — IDF-weighted overlap of de-pluralized content terms;
   this is also the primary **abstention** signal: a query whose distinctive
   terms appear nowhere scores low everywhere and returns no evidence.
4. **Exact identifiers** — CVE/CWE/CAPEC/ATT&CK matches qualify and boost.
5. **Fusion & optional rerank** — normalized vector + lexical scores, plus an
   identifier boost; optional cheap lexical rerank (no heavy model in the path).

Every returned **evidence object** carries document id, chunk id, title, source
URL/reference, text, page number, section heading, retrieval method, score, and
collection ids. Citations always reference real stored chunks.

## Grounded answering

The trusted system prompt instructs the model to answer only from evidence, cite
labels, flag conflicts, state uncertainty, and **treat the evidence block as
untrusted data** — never as instructions. The model is given no tools, so
retrieved content cannot trigger tool execution or secret disclosure. With no
evidence, the service abstains instead of inventing an answer.

## Provider abstractions

- **Embeddings** and **generation** are each an abstract interface with three
  implementations: `fake` (deterministic/offline), `ollama`, `openai`
  (OpenAI-compatible). Selected and configured entirely via environment
  variables. Each embedding provider exposes a `version` string recorded on
  every chunk.
- **Vector store**: `memory` (numpy over DB-persisted vectors; default) or
  `qdrant`. Security is enforced in the service layer regardless of backend.
- **Storage**: a small `LocalStorage` interface for raw bytes, designed to be
  swapped for object storage.

## External interfaces

- **REST API** under `/api/v1` (see [API.md](API.md)). Dual auth: JWT (web) or
  `X-API-Key` (external). Admin/web-only operations reject API keys.
- **MCP adapter** (`app/mcp`): a dependency-free JSON-RPC stdio server exposing
  four read-only tools over the same authorized service layer.

## Deployment

`docker compose` brings up PostgreSQL, the backend (migrations + bootstrap on
start), and the frontend; Qdrant and Ollama are optional profiles. The backend
image runs as a non-root user with a health check. A native (non-Docker) path is
fully supported for development.
