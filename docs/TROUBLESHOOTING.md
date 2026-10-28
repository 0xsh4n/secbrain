# Troubleshooting

## Setup

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
(`npm run build`) or use `npm run dev`. Ensure the backend's
`SECBRAIN_CORS_ORIGINS` includes the frontend origin (e.g. `http://localhost:3000`).

## Database & migrations

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

## Ingestion

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

## Models / chat

**Chat returns 503 "Generation model unavailable".**
No reachable generation model. Configure one (see
[LOCAL_MODELS.md](LOCAL_MODELS.md)) or keep the default `fake` provider.
Retrieval and document management work regardless.

**Ollama configured but model "not pulled".**
`ollama pull <model>` first; `SECBRAIN_LLM_MODEL` must match a pulled model.
Check `/api/v1/models/status`.

**Answers reference the wrong number of sources / no citations.**
With the `fake` provider, generation is deterministic and not natural language —
configure a real model for synthesis. Retrieval quality is independent and can be
measured with `python -m eval.run_eval`.

## Docker

**`backend` unhealthy / restarts.**
It waits for `db` to be healthy, then runs migrations. Check
`docker compose logs backend`. Ensure `SECBRAIN_DATABASE_URL` points at the `db`
service and `SECBRAIN_SECRET_KEY` is set.

**Qdrant/Ollama not running.**
They are opt-in profiles: `docker compose --profile qdrant --profile models up`.
With defaults (`VECTOR_STORE=memory`, `*_PROVIDER=fake`) neither is required.

**Low memory on the host.**
Don't run Postgres + Qdrant + Ollama + both app servers at once on a ~4 GB box.
Start with the offline defaults and enable heavy services one at a time.

## Tests / eval

**`pytest` uses my real DB.**
It doesn't — `tests/conftest.py` sets a temporary SQLite DB before importing the
app and truncates tables between tests.

**Eval harness fails a gate.**
`python -m eval.run_eval` prints per-question results and the failing metric
(recall/MRR/citation/abstention). It uses a throwaway DB and the deterministic
providers, so failures indicate a real regression in retrieval/grounding.
