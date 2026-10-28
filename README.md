# SecBrain

**A model-independent cybersecurity knowledge platform, GenAI copilot, and agent runtime.**

SecBrain collects, processes, organizes, indexes, and retrieves security knowledge (articles, PDFs, Markdown/HTML/DOCX, notes, public URLs). It exposes this intelligence through a responsive dark web UI, voice chat, a versioned REST API, and a read-only Model Context Protocol (MCP) server for external AI agents.

**Core principle:** SecBrain owns and manages the security knowledge. The underlying LLM is **replaceable without rebuilding the knowledge base**. RAG supplies relevant context at inference time — it does not fine-tune or modify model weights.

---

## Highlights

- **SecBrain Copilot** — A friendly, professional cybersecurity engineering assistant that answers technical questions, generates production-ready code (Python, Bash, YARA, configs), and suggests remediations.
- **Voice Chat ("Operator Nyx")** — Browser speech recognition with live transcript feedback, spoken responses, an audio visualizer, and a text fallback.
- **Real-Time Streaming & Code Blocks** — Word-by-word token streaming via Server-Sent Events (SSE) with formatted syntax cards and 1-click **"Copy code"** buttons.
- **Persistent Multi-Turn Chat** — Database-backed conversation threads with history switching and context from earlier messages in the active conversation.
- **Responsive Workspace** — Desktop navigation rail, compact mobile navigation, touch-friendly controls, and layouts that adapt across the dashboard, library, search, ingest, and chat screens.
- **Hybrid Retrieval** — Semantic (vector) + IDF-weighted keyword + metadata filtering + exact security-identifier boosting (CVE/CWE/CAPEC/ATT&CK), behind strict multi-tenant authorization.
- **Model-Independent & Hardware-Tuned** — Pluggable providers (deterministic offline default, Ollama, OpenAI-compatible). Specifically optimized for budget hardware and consumer GPUs (e.g. 4 GB VRAM / GTX 1650).
- **Ingestion State Machine** — PDF/TXT/MD/HTML/DOCX/text/URL processing with duplicate detection, SSRF protection, heading-aware chunking, embeddings, and automatic retry.
- **Multi-Agent Architecture (MCP)** — Built-in Model Context Protocol stdio server allowing Claude Desktop, Cursor, and autonomous agents to query SecBrain as their central security library.
- **Quality Checks** — Backend test suite covering auth, SSRF, extraction, ingestion, retrieval, authorization, API keys, and MCP, plus a deterministic retrieval-evaluation harness.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system design and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the security boundary model.

---

## Quick Start (Docker — Recommended)

```bash
# 1. Copy environment template
cp .env.example .env            # review and adjust secrets

# 2. Build and launch all containers
docker compose up --build
```

Then open:

- **Web UI:** <http://localhost:3000>
- **Knowledge Chat & Live Call:** <http://localhost:3000/chat>
- **API Docs (Swagger UI):** <http://localhost:8000/docs>
- **Health Check:** <http://localhost:8000/api/v1/health>

On first start, the backend runs migrations, bootstraps the admin account, and (if `SECBRAIN_SEED_SAMPLES_ON_START=true` in `.env`) ingests the sample corpus. Log in with the admin credentials from your `.env`.

Optional Docker profiles:

```bash
docker compose --profile qdrant up --build     # also start Qdrant vector store
docker compose --profile models up --build      # also start Ollama inside Docker
```

---

## Quick Start (Native Development, No Docker)

Requires Python 3.12+ (3.14 verified) and Node 20+.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate                      # On Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                           # defaults are offline/SQLite

alembic upgrade head                           # run database migrations
python -m app.cli bootstrap                    # create admin + default collections
python -m app.cli seed-samples                 # (optional) ingest the sample corpus

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local               # points at http://localhost:8000
npm run dev                                    # http://localhost:3000
```

Default bootstrap admin: `admin@secbrain.local` / `changeme-admin-123` (**change in production**).

---

## Platform Features

1. **Ingest** — Ingestion Queue page: paste text, submit public URLs, or upload PDF/MD/HTML/DOCX files. Tracks progress through `PENDING → FETCHING → EXTRACTING → INDEXING → COMPLETED`. After successful indexing, uploaded source files are discarded; extracted text and indexed chunks stay in the knowledge pool.
2. **Search** — Search page: hybrid retrieval returning authorized evidence passages with source metadata, score, and retrieval method tags.
3. **Knowledge Chat & Copilot** — Chat page: multi-turn conversation threads, real-time streaming, rich syntax code blocks with 1-click copy, and persistent topic history.
4. **Voice Chat** — Use the microphone for speech-to-text or open **`Call`** for a continuous listen/respond voice session. Browser speech recognition support and network access are required; typed input remains available as a fallback.
5. **API Keys & MCP** — Create scoped, rate-limited API keys for external applications or connect agents via the stdio MCP server.

### Example API Usage

```bash
# 1. Log in to get an access token
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@secbrain.local","password":"changeme-admin-123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. Hybrid search across indexed knowledge
curl -s -X POST localhost:8000/api/v1/knowledge/search \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"query":"Which Log4j versions are affected by CVE-2021-44228?","top_k":3}'
```

More examples (including chat sessions, SSE streaming, and MCP setup) in [docs/API.md](docs/API.md).

### Knowledge Pool, Backups, and Google Drive

The durable library is extracted text, document metadata, chunks, and embeddings. SecBrain removes uploaded source files after indexing completes, while keeping enough extracted content to search, answer questions, and rebuild the index. Failed or unfinished ingests retain their source so they can be retried. Existing completed uploads are cleaned up when the backend next starts.

Use **Settings → Library backup & restore** to export a ZIP containing extracted knowledge and metadata, then restore it on another PC. The ZIP does not contain original PDFs, conversations, users, API keys, or model configuration. Optional Google Drive sync keeps the knowledge pool synchronized across local installations; configure the Google OAuth client ID and secret in the backend environment first. See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#knowledge-backup-and-google-drive-sync) for setup notes.

Chat is not model-weight training. New ingested documents expand retrieval context; earlier messages inform answers in their own conversation. Ollama does not silently fine-tune itself from chat transcripts.

---

## Local Models & Hardware Optimization

SecBrain runs fully offline by default. To enable natural-language generation and semantic vector search using local hardware:

### Running Ollama on Host (with SecBrain in Docker)

```bash
# 1. Pull lightweight, high-performance models on your host
ollama pull qwen2.5:3b              # Best balance for <= 4 GB VRAM
ollama pull nomic-embed-text        # 768-dim embeddings (274 MB)
```

In `.env`:
```ini
# Connect Docker container to Ollama on host
SECBRAIN_EMBEDDING_PROVIDER=ollama
SECBRAIN_EMBEDDING_BASE_URL=http://host.docker.internal:11434
SECBRAIN_EMBEDDING_MODEL=nomic-embed-text
SECBRAIN_EMBEDDING_DIM=768

SECBRAIN_LLM_PROVIDER=ollama
SECBRAIN_LLM_BASE_URL=http://host.docker.internal:11434
SECBRAIN_LLM_MODEL=qwen2.5:3b
SECBRAIN_LLM_CONTEXT_TOKENS=4096
SECBRAIN_LLM_MAX_OUTPUT_TOKENS=512
SECBRAIN_LLM_TIMEOUT_SECONDS=300
SECBRAIN_RETRIEVAL_TOP_K=4
```

See [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md) for hardware tiers, VRAM sizing, and performance benchmarks.

---

## Quality Gates & Testing

```bash
# Backend test suite (auth, SSRF, ingestion, retrieval, MCP)
cd backend && pytest -v

# Retrieval & grounding evaluation harness
python -m eval.run_eval

# Frontend compilation & type-checking
cd ../frontend && npm run build
```

---

## Documentation Index

- [Architecture Design](docs/ARCHITECTURE.md)
- [Threat Model & Security Boundaries](docs/THREAT_MODEL.md)
- [REST API & Integration Guide](docs/API.md)
- [Local Models & Hardware Sizing](docs/LOCAL_MODELS.md)
- [Multi-Agent Testing Architecture](docs/AGENTS.md)
- [Developer & Contributor Guide](CONTRIBUTING.md)
- [Troubleshooting Common Issues](docs/TROUBLESHOOTING.md)
- [Known Limitations](docs/LIMITATIONS.md)
- [Environment Report](docs/ENVIRONMENT_REPORT.md)
