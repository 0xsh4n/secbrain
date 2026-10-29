# SecBrain

**A model-independent cybersecurity knowledge platform, GenAI copilot, and agent runtime.**

SecBrain collects, processes, organizes, indexes, and retrieves security knowledge (articles, PDFs, Markdown/HTML/DOCX, notes, public URLs). It exposes this intelligence through a responsive dark web UI, voice chat, a versioned REST API, and a read-only Model Context Protocol (MCP) server for external AI agents.

**Core principle:** SecBrain owns and manages the security knowledge. The underlying LLM is **replaceable without rebuilding the knowledge base**. RAG supplies relevant context at inference time — it does not fine-tune or modify model weights.

---

## Highlights

- **Nyx, the SecBrain Copilot** — A friendly, professional cybersecurity engineering assistant that answers technical questions, generates production-ready code (Python, Bash, YARA, configs), and suggests remediations.
- **Natural Voice (Nyx) + Hands-Free Wake Word** — Spoken replies use a local **Piper neural voice** (warm and human-like, runs on CPU, offline) with automatic fallback to browser speech. A full live-call mode, in-composer dictation, and an optional **wake word** ("Nyx" / "Hey Nyx") that opens the call hands-free.
- **Scope-Gated System Actions** — Opt-in, fail-closed action layer that can run `nmap` against **authorized targets only** (engagement scope / allowlist) and launch **allowlisted applications** — driven by your direct command, never by the LLM or ingested content, and fully audited.
- **Works from any device on your network** — The browser resolves the API at runtime, so opening the app from a phone or another machine just works (no rebuild).
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
cp .env.local.example .env.local               # optional; defaults auto-derive the API from the browser host
npm run dev                                    # http://localhost:3000
```

Default bootstrap admin: `admin@secbrain.local` / `changeme-admin-123` (**change in production**).

> For remote dev access, bind the backend to all interfaces:
> `uvicorn app.main:app --host 0.0.0.0 --port 8000`, and start the frontend with
> `npm run dev -- -H 0.0.0.0`.

---

## Accessing SecBrain from Other Devices (Remote / Network Access)

The frontend resolves the API base URL **at runtime in the browser**, so the app
works from a phone or another machine with no rebuild. `localhost` is never baked
into the client bundle. Pick whichever fits your setup:

| Scenario | Frontend (`.env.local` / build args) | Backend |
|----------|--------------------------------------|---------|
| **LAN / self-hosted (default)** | Leave `NEXT_PUBLIC_API_URL` unset. Optionally set `NEXT_PUBLIC_API_PORT` (default `8000`). Opening `http://<server-ip>:3000` makes the API target `http://<server-ip>:8000` automatically. | Reachable on that host:port, and `SECBRAIN_CORS_ALLOW_ALL=true` (default in docker-compose) **or** list the exact origin in `SECBRAIN_CORS_ORIGINS`. Bind `--host 0.0.0.0`. |
| **Fixed public URL** | `NEXT_PUBLIC_API_URL=https://api.your-domain.example` | Allow that frontend origin via `SECBRAIN_CORS_ORIGINS`. |
| **Single URL / tunnel (reverse proxy)** | `NEXT_PUBLIC_API_URL=same-origin` (browser uses relative `/api` paths) | Put a proxy in front that routes `/api/*` to the backend. No CORS needed — ideal for Cloudflare Tunnel / ngrok / a single forwarded port. |

CORS note: because authentication uses a **Bearer token header (not cookies)**,
`SECBRAIN_CORS_ALLOW_ALL=true` runs with credentials disabled and is safe for a
self-hosted single-tenant deployment. Lock it down by setting it to `false` and
listing exact origins in `SECBRAIN_CORS_ORIGINS`.

With Docker, `docker compose up` already binds `0.0.0.0`, enables
`SECBRAIN_CORS_ALLOW_ALL`, and builds the frontend to auto-derive the API — just
open `http://<server-ip>:3000` from any device on the network.

---

## Platform Features

1. **Ingest** — Ingestion Queue page: paste text, submit public URLs, or upload PDF/MD/HTML/DOCX files. Tracks progress through `PENDING → FETCHING → EXTRACTING → INDEXING → COMPLETED`. After successful indexing, uploaded source files are discarded; extracted text and indexed chunks stay in the knowledge pool.
2. **Search** — Search page: hybrid retrieval returning authorized evidence passages with source metadata, score, and retrieval method tags.
3. **Knowledge Chat & Copilot** — Chat page: multi-turn conversation threads, real-time streaming, rich syntax code blocks with 1-click copy, and persistent topic history.
4. **Voice Chat (Nyx)** — Click the 🎙️ mic to dictate, or open **`📞 Live Call`** for a continuous listen/respond session. Nyx speaks with a local Piper neural voice (falls back to browser speech if the voice model isn't installed). Toggle **👂 Wake** and say "Nyx" to start a call hands-free. Speech-to-text uses the browser's recognition service (Chrome/Edge); typed input is always available.
5. **System Actions (optional, admins)** — When enabled, type or say a command like `scan quick 127.0.0.1` or `open firefox`; SecBrain parses it, asks you to confirm, runs it only if the target is in authorized scope, and shows the result. Disabled by default — see [System actions](#system-actions-nmap--app-launch).
6. **API Keys & MCP** — Create scoped, rate-limited API keys for external applications or connect agents via the stdio MCP server.

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

## Nyx's Voice (Local Neural TTS)

Nyx speaks with **Piper**, a local neural text-to-speech engine that runs on CPU,
offline, with no GPU. The voice model is downloaded once:

```bash
cd backend && source .venv/bin/activate
python -m app.cli download-voice          # downloads en_US-amy-medium (~63 MB)
```

Relevant settings (see `backend/.env.example`):

```ini
SECBRAIN_TTS_PROVIDER=piper               # or "none" to disable
SECBRAIN_TTS_VOICE_NAME=Nyx
SECBRAIN_PIPER_VOICE_PATH=./data/voices/en_US-amy-medium.onnx
SECBRAIN_TTS_LENGTH_SCALE=1.0             # >1 slower, <1 faster
```

In Docker the model is fetched automatically on first start. If the voice model
is missing, the TTS endpoint returns `503` and the UI **falls back to the
browser's built-in speech synthesis**, so voice still works everywhere. Speech
recognition (dictation, wake word, live-call listening) uses the browser's own
service and works best in Chrome/Edge.

---

## System Actions (nmap / app launch)

An opt-in, **fail-closed** action layer lets Nyx run a small set of system
actions on your direct command. It is **disabled by default**.

Enable and scope it in the backend environment:

```ini
SECBRAIN_ACTIONS_ENABLED=true
# Authorized scan targets (lab/loopback). Prefer defining scope via an Engagement.
SECBRAIN_ACTION_SCOPE_ALLOWLIST=["127.0.0.1/32","192.168.56.0/24"]
# Only these apps can be launched (friendly name -> argv):
SECBRAIN_ALLOWED_APPS={"firefox":["firefox"],"burp":["BurpSuiteCommunity"]}
```

Then, in chat (as an admin), type or say:

- `scan quick 127.0.0.1` — nmap quick scan (profiles: `quick`, `service`, `top100`, `ping`)
- `open firefox` — launch an allowlisted application

SecBrain parses the command, **asks you to confirm**, and executes only if the
target is within an authorized scope. Safeguards:

- Off unless explicitly enabled; refuses anything outside scope (targets, apps).
- Admin **session** only — not reachable with an API key.
- No shell is used (argv lists); nmap flags come from fixed profiles, not free-form input.
- The executor is driven by your direct, structured command — **never by the LLM
  or by text inside an ingested document** (no prompt-injection → command execution).
- Every action (and refusal) is audit-logged.

> ⚠️ Only scan systems you are authorized to test. App launch runs on the host
> where the backend runs, so it is most useful in the **native** deployment on
> your workstation (inside a container it launches within the container).

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the full security rationale.

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
