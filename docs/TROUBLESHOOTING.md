# Troubleshooting

## Setup & Environment

**`pip install` fails building a package.**  
All pinned dependencies ship prebuilt wheels for Python 3.12–3.14. Upgrade pip
(`pip install -U pip`) and ensure you're on a supported Python. The Docker image
uses Python 3.12.

**Port 8000 or 3000 already in use.**  
Another service may hold the port. Run the backend on another port
(`uvicorn app.main:app --port 8010`) and set the frontend's
`NEXT_PUBLIC_API_URL` to match (rebuild the frontend or use `next dev`, which
reads env at runtime).

**Frontend can't reach the API / CORS errors.**  
`NEXT_PUBLIC_API_URL` is inlined at **build time**. After changing it, rebuild
(`docker compose up --build` or `npm run build`). Ensure the backend's
`SECBRAIN_CORS_ORIGINS` includes the frontend origin (e.g. `http://localhost:3000`).

---

## Local Models & Ollama

**Generation model shows "Offline" / connection refused.**  
When running SecBrain in Docker and Ollama on your host machine, `http://localhost:11434` does not reach your host (it loops back inside the container).  
* **Fix:** In `.env`, set:
  ```ini
  SECBRAIN_LLM_BASE_URL=http://host.docker.internal:11434
  SECBRAIN_EMBEDDING_BASE_URL=http://host.docker.internal:11434
  ```

**"Generation model unavailable: timed out" in Chat.**  
This happens when Ollama takes longer to load weights from disk or compute the prompt than the HTTP client timeout. Common causes and fixes:
1. **Cold-load latency:** Run `ollama run <model> "hello"` once on the host to pre-warm the model into RAM/VRAM before using the web app. SecBrain automatically sends `"keep_alive": "30m"` to keep it warm.
2. **Context & chunk size too large:** In `.env`, set `SECBRAIN_LLM_CONTEXT_TOKENS=4096` and `SECBRAIN_RETRIEVAL_TOP_K=4` to reduce prompt evaluation time.
3. **Model too large for VRAM:** If a model's weights exceed available VRAM (e.g. running a 4 GB model on a 4 GB VRAM GPU), layers spill into system RAM and CPU, slowing token generation to a crawl. Switch to a compact model like `qwen2.5:3b` (~1.9 GB) or `llama3.2:3b`.
4. **Increase timeout:** Set `SECBRAIN_LLM_TIMEOUT_SECONDS=300` in `.env` to give slower hardware 5 minutes before aborting.

**Ollama configured but model "not pulled".**  
You must pull the exact model tag on your Ollama host first:
```bash
ollama pull <model-name>
```
Verify with `ollama list` and check `http://localhost:8000/api/v1/models/status`.

**Embedding model mismatch / errors during ingestion.**  
If using `SECBRAIN_EMBEDDING_PROVIDER=ollama`, you must specify both the model and its dimension:
```ini
SECBRAIN_EMBEDDING_MODEL=nomic-embed-text
SECBRAIN_EMBEDDING_DIM=768
```
Without these, the system defaults to `fake-hash-256` which will fail against Ollama.

---

## Database & Migrations

**`alembic upgrade head` does nothing / wrong DB.**  
Alembic reads `SECBRAIN_DATABASE_URL` from the environment (see
`alembic/env.py`). Export it (or set it in `.env`) before running.

**Switching SQLite ↔ Postgres.**  
They are separate databases. Run `alembic upgrade head` against the new URL;
`python -m app.cli bootstrap` to create the admin; re-ingest or
`seed-samples` as needed. The Postgres URL uses the psycopg3 driver:
`postgresql+psycopg://user:pass@host:5432/db`.

**Login fails after a fresh DB.**  
Run `python -m app.cli bootstrap` (native) — the Docker entrypoint does this
automatically. Default admin is `SECBRAIN_BOOTSTRAP_ADMIN_EMAIL` /
`…_PASSWORD`.

---

## Ingestion & Retrieval

**A URL won't ingest / "URL rejected by SSRF policy".**  
By design: loopback, private, link-local, metadata, and reserved addresses are
blocked, as are non-http(s) schemes and unexpected content types. For internal
test hosts in a trusted environment only, set
`SECBRAIN_ALLOW_PRIVATE_URL_FETCH=true` (never in production).

**A document shows status `failed`.**  
Open the document detail page for the extraction error (e.g. scanned/image-only
PDF with no text, unreadable DOCX). Fix the source and use **Reprocess**. Jobs
are retryable.

**A document is flagged `duplicate`.**  
Its normalized content hash matches an already-indexed document in the same org.
Duplicates are recorded (and point at the original) but not re-embedded, to save
compute and avoid double-returning the same evidence.

**Search returns nothing relevant / abstains.**  
This is intended when the knowledge base has nothing matching the query's
distinctive terms. Ingest relevant documents, widen the collection selection, or
lower `SECBRAIN_RETRIEVAL_MIN_LEXICAL`. If you switched embedding models,
**reprocess** documents so chunks are re-embedded in the current space.

---

## Docker

**`backend` unhealthy / restarts.**  
It waits for `db` to be healthy, then runs migrations. Check
`docker compose logs backend`. Ensure `SECBRAIN_DATABASE_URL` points at the `db`
service and `SECBRAIN_SECRET_KEY` is set.

**Qdrant/Ollama not running in Docker.**  
They are opt-in profiles: `docker compose --profile qdrant --profile models up`.
With defaults (`VECTOR_STORE=memory`, `*_PROVIDER=fake`) neither is required.

**Low memory on the host.**  
Don't run Postgres + Qdrant + Ollama + both app servers at once on an 8 GB box.
Run Ollama on the host and SecBrain in Docker, or use lightweight models (`qwen2.5:3b`, `qwen2.5:1.5b`).

---

## Tests / Eval

**`pytest` uses my real DB.**  
It doesn't — `tests/conftest.py` sets a temporary SQLite DB before importing the
app and truncates tables between tests.

**Eval harness fails a gate.**  
`python -m eval.run_eval` prints per-question results and the failing metric.
Ensure the test environment has the expected model configurations exported.
