# Environment Report

Captured during initial development on the target build machine.

## Host

| Item | Value |
|------|-------|
| OS | Kali GNU/Linux Rolling (2026.3), kernel 7.1.5, x86_64 |
| Virtualization | VMware (VMware SVGA II display adapter) |
| GPU | **None detected** (no `nvidia-smi`, no discrete GPU). CPU-only. |
| CPU | 4 cores |
| System memory | 4.8 GB total, ~2.3 GB available at inspection |
| Disk | 71 GB free |
| Python | 3.14.7 (`/usr/bin/python3`) |
| Node.js | v24.19.0 |
| npm | 11.19.0 |
| Docker | 28.5.2, Docker Compose 2.40.3 |
| Git | 2.53.0 |

## Implications for the design

The machine is **CPU-only with constrained RAM**. SecBrain is therefore designed
so the core knowledge platform runs with no GPU, no external model, and no extra
services:

- **Default embeddings**: a deterministic hash embedder (no model download, no
  GPU, reproducible). Real semantic embeddings are opt-in via Ollama/OpenAI.
- **Default generation**: a deterministic offline provider. Real generation is
  opt-in. Retrieval and document management never depend on a generation model.
- **Default vector store**: in-process numpy cosine over embeddings persisted in
  the primary database. Qdrant is optional.
- **Default database**: SQLite for native dev/tests (zero infra). PostgreSQL is
  used under Docker and is fully supported.

All backend dependencies install from **prebuilt binary wheels on Python 3.14**
(verified): fastapi, uvicorn, pydantic, SQLAlchemy, alembic, psycopg[binary],
bcrypt, PyJWT, httpx, pypdf, python-docx, beautifulsoup4, lxml, numpy,
qdrant-client, slowapi, pytest. No source compilation is required.

## Recommended configuration on this class of hardware

| Scenario | Recommended settings |
|----------|----------------------|
| Fastest / offline (default) | `EMBEDDING_PROVIDER=fake`, `LLM_PROVIDER=fake`, `VECTOR_STORE=memory`, SQLite |
| Real local models (≤4 GB VRAM or CPU) | Ollama with a small quantized model, e.g. `qwen3:4b` or an embedding model like `nomic-embed-text`. Expect slow CPU generation. |
| Production | PostgreSQL + (optionally) Qdrant + an OpenAI-compatible or Ollama endpoint. |

> On a 4 GB-VRAM / low-RAM host, do not run Ollama (a 4B model), PostgreSQL,
> Qdrant, and both app servers simultaneously. Start with the offline defaults
> and enable heavier components one at a time.
