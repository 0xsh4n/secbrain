# SecBrain

**A model-independent cybersecurity knowledge platform.**

SecBrain collects, processes, organizes, indexes, and retrieves security
knowledge (articles, PDFs, Markdown/HTML/DOCX, pasted notes, public URLs), and
exposes it through a web UI, a versioned REST API, and a read-only MCP adapter so
that other AI applications and future security agents can retrieve relevant
information.

**Core principle:** SecBrain owns and manages the knowledge. Connected AI apps
use that knowledge for their own tasks. The underlying LLM is **replaceable
without rebuilding the knowledge base**. RAG supplies relevant context at
inference time — it does not fine-tune or modify model weights.

---

## Highlights

- **Hybrid retrieval** — semantic (vector) + IDF-weighted keyword + metadata
  filtering + exact security-identifier boosting (CVE/CWE/CAPEC/ATT&CK), behind
  a permission filter. Abstains honestly when evidence is missing.
- **Model-independent** — pluggable embedding and generation providers (offline
  deterministic default, Ollama, OpenAI-compatible). Works with **no GPU and no
  model** for search and document management.
- **Real ingestion pipeline** — PDF/TXT/MD/HTML/DOCX/text/URL with a state
  machine, duplicate detection, SSRF-protected URL fetching, chunking,
  embeddings, indexing, retry.
- **Multi-tenant & access-controlled** — organizations, collections
  (private/organization), per-document ownership; retrieval enforces
  authorization before returning evidence.
- **External integration** — versioned REST API with hashed, scoped,
  rate-limited API keys; a read-only MCP server over the same authorized layer.
- **Tested** — 45 backend tests (auth, SSRF, extraction, ingestion, retrieval,
  authorization, API keys, MCP) plus a deterministic retrieval-evaluation
  harness. Frontend builds clean.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the security model.

---

## Quick start (Docker — recommended)

```bash
cp .env.example .env            # review; change SECBRAIN_SECRET_KEY and admin password
docker compose up --build
```

Then open:

- Web UI: <http://localhost:3000>
- API docs (Swagger): <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health>

On first start the backend runs migrations, creates the bootstrap admin, and
(if `SECBRAIN_SEED_SAMPLES_ON_START=true` in `.env`) ingests the sample corpus.
Log in with the admin email/password from your `.env`.

Optional profiles:

```bash
docker compose --profile qdrant up --build     # also start Qdrant (set SECBRAIN_VECTOR_STORE=qdrant)
docker compose --profile models up --build      # also start Ollama (then pull a model, see below)
```

---

## Quick start (native, no Docker)

Requires Python 3.12+ (3.14 verified) and Node 20+.

### Backend

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # defaults are offline/SQLite — fine as-is

alembic upgrade head                      # initialize the database (migrations)
python -m app.cli bootstrap               # create admin + default collections
python -m app.cli seed-samples            # (optional) ingest the sample corpus

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local          # points at http://localhost:8000
npm run dev                               # http://localhost:3000
```

Default bootstrap admin: `admin@secbrain.local` / `changeme-admin-123`
(**change it**; configurable via `SECBRAIN_BOOTSTRAP_ADMIN_*`).

---

## Using it

1. **Ingest** — Ingestion Queue page: paste text, submit a public URL, or upload
   a PDF/MD/HTML/DOCX. Watch the job progress through
   `PENDING → FETCHING → EXTRACTING → INDEXING → COMPLETED`.
2. **Search** — Search page: hybrid retrieval returns evidence passages with
   source metadata, score, and the retrieval method used.
3. **Chat** — Knowledge Chat: ask grounded questions; answers cite the evidence
   used and link back to the source documents. Clear error if no model is
   configured.
4. **API keys** — create a scoped, rate-limited key (shown once) for external AI
   apps and the MCP adapter.

### Call the API

```bash
# Log in (or use an API key instead of the bearer token)
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@secbrain.local","password":"changeme-admin-123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Search
curl -s -X POST localhost:8000/api/v1/knowledge/search \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"query":"Which Log4j versions are affected by CVE-2021-44228?","top_k":3}'
```

More examples (including API-key and MCP usage) in [docs/API.md](docs/API.md).

---

## Configure a local model (optional)

SecBrain runs fully offline by default. To get natural-language generation and
semantic embeddings, point it at **Ollama** or any **OpenAI-compatible**
endpoint — **no source changes required**, only environment variables. See
[docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md).

---

## Tests, eval, and quality gates

```bash
cd backend && . .venv/bin/activate
pytest                      # 45 tests
python -m eval.run_eval     # retrieval/grounding evaluation (recall, MRR, citation, abstention)

cd ../frontend
npm run build               # production build (type-check + compile)
```

---

## Project layout

```
secbrain/
  backend/      FastAPI app, services, models, migrations, tests, eval, samples, MCP
  frontend/     Next.js + TypeScript + Tailwind web UI
  docs/         Architecture, threat model, API, local models, troubleshooting, limitations
  docker-compose.yml
  .env.example
```

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for known limitations and security
assumptions, and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common
issues.

---

## Documentation index

- [Architecture](docs/ARCHITECTURE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [API usage & examples](docs/API.md)
- [Local model configuration](docs/LOCAL_MODELS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Known limitations & security assumptions](docs/LIMITATIONS.md)
- [Environment report](docs/ENVIRONMENT_REPORT.md)
