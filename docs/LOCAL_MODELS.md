# Local Model Configuration

SecBrain is model-independent. Generation and embedding providers are selected
and configured **entirely via environment variables** — no source changes. The
knowledge base (ingestion, search, document management) works with **no model at
all**; a generation model only affects the natural-language answer synthesis in
chat and `/knowledge/answer`.

## Providers

| Variable | Values | Meaning |
|---|---|---|
| `SECBRAIN_LLM_PROVIDER` | `fake` / `ollama` / `openai` | Generation backend |
| `SECBRAIN_EMBEDDING_PROVIDER` | `fake` / `ollama` / `openai` | Embedding backend |

- `fake` — deterministic, offline, no GPU. Default. The embedder is a stable
  hashing embedder; the generator composes a grounded, citation-shaped response
  from the evidence (useful for dev/tests, not for natural language).
- `ollama` — a local [Ollama](https://ollama.com) server.
- `openai` — any OpenAI-compatible `/v1/chat/completions` and `/v1/embeddings`
  endpoint (OpenAI, vLLM, LM Studio, LocalAI, etc.).

---

## Hardware Sizing & Recommended Models

When choosing models for local inference, your **VRAM (GPU memory)** and **System RAM** dictate what will run smoothly:

> [!IMPORTANT]
> Models must fit entirely within your free VRAM for fast, interactive responses (30–60+ tokens/sec). If a model's size exceeds available VRAM, Ollama offloads layers to system RAM and CPU, which can slow down generation by 10x–20x and cause timeouts.
> Remember: The OS and desktop display (Windows DWM / X11) consume ~0.5–0.8 GB VRAM on their own.

### Hardware Tiers & Tested Configurations

#### Tier 1: Low-Memory / Budget GPUs (4 GB VRAM, 8–16 GB RAM)
*Example hardware: Nvidia GTX 1650, RTX 3050 (4GB), GTX 1050 Ti, Apple M1/M2 (8GB unified).*
* Target model weight size: **≤ 2.2 GB**
* **Recommended LLM:** `qwen2.5:3b` (~1.9 GB) or `llama3.2:3b` (~2.0 GB)
* **Ultra-fast LLM:** `qwen2.5:1.5b` (~1.0 GB)
* **Embedding Model:** `nomic-embed-text` (~274 MB, 768-dim)
* **Combined footprint:** ~2.2 GB VRAM total — fits 100% inside 4 GB VRAM with plenty of headroom for desktop rendering and KV cache.

#### Tier 2: Mid-Range GPUs (6–8 GB VRAM, 16–32 GB RAM)
*Example hardware: Nvidia RTX 3060, RTX 4060, Apple M-series (16GB+).*
* Target model weight size: **≤ 5.0 GB**
* **Recommended LLM:** `qwen2.5:7b` (~4.7 GB) or `llama3.1:8b` (~4.9 GB)
* **Embedding Model:** `nomic-embed-text` (768-dim) or `mxbai-embed-large` (1024-dim, ~670 MB)

#### Tier 3: CPU Only / Air-Gapped Environments
* If no dedicated GPU is available, stick to **`qwen2.5:1.5b`** or **`all-minilm`** (384-dim embedder, ~45 MB) to avoid CPU generation lag, or use the default `fake` provider.

---

## Example: Ollama Configuration

### 1. Ollama on Host Machine, SecBrain in Docker (Most Common)

When Ollama runs directly on your Windows/macOS/Linux host and SecBrain runs inside Docker Compose, the container cannot use `localhost` (which refers to the container itself). Use **`host.docker.internal`**:

```bash
# Pull models on host:
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

`.env`:
```ini
# --- Embedding Model ---
SECBRAIN_EMBEDDING_PROVIDER=ollama
SECBRAIN_EMBEDDING_BASE_URL=http://host.docker.internal:11434
SECBRAIN_EMBEDDING_MODEL=nomic-embed-text
SECBRAIN_EMBEDDING_DIM=768

# --- Generation Model ---
SECBRAIN_LLM_PROVIDER=ollama
SECBRAIN_LLM_BASE_URL=http://host.docker.internal:11434
SECBRAIN_LLM_MODEL=qwen2.5:3b
SECBRAIN_LLM_CONTEXT_TOKENS=4096
SECBRAIN_LLM_MAX_OUTPUT_TOKENS=512
SECBRAIN_LLM_TEMPERATURE=0.1
SECBRAIN_LLM_TIMEOUT_SECONDS=300

# --- Retrieval Tuning (Reduces prompt size & speed up responses) ---
SECBRAIN_RETRIEVAL_TOP_K=4
```

### 2. Native Setup (Both Ollama & SecBrain on Host, No Docker)

If running SecBrain directly with Python and Node:
```ini
SECBRAIN_EMBEDDING_BASE_URL=http://localhost:11434
SECBRAIN_LLM_BASE_URL=http://localhost:11434
```

### 3. Ollama in Docker via Profile

If using the compose `models` profile (`docker compose --profile models up`):
```ini
SECBRAIN_EMBEDDING_BASE_URL=http://ollama:11434
SECBRAIN_LLM_BASE_URL=http://ollama:11434
```

---

## Example: OpenAI-Compatible Endpoint

Works with OpenAI, vLLM, LM Studio, LocalAI, or Groq:

```ini
SECBRAIN_LLM_PROVIDER=openai
SECBRAIN_LLM_MODEL=gpt-4o-mini
SECBRAIN_LLM_BASE_URL=https://api.openai.com
SECBRAIN_LLM_API_KEY=sk-...

SECBRAIN_EMBEDDING_PROVIDER=openai
SECBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECBRAIN_EMBEDDING_DIM=1536
SECBRAIN_EMBEDDING_BASE_URL=https://api.openai.com
SECBRAIN_EMBEDDING_API_KEY=sk-...
```

---

## Tunable Model Settings Reference

| Variable | Default | Purpose |
|---|---|---|
| `SECBRAIN_LLM_CONTEXT_TOKENS` | `8192` (tuned to `4096`) | Context window size in tokens (`num_ctx`). Lowering to 4096 or 2048 saves VRAM and speeds up prompt prefill. |
| `SECBRAIN_LLM_MAX_OUTPUT_TOKENS` | `1024` (tuned to `512`) | Max generated tokens per response. 512 is plenty for grounded security summaries. |
| `SECBRAIN_LLM_TEMPERATURE` | `0.1` | Sampling temperature (0.0 = fully deterministic, 0.7 = creative). |
| `SECBRAIN_LLM_TIMEOUT_SECONDS` | `120.0` (tuned to `300.0`) | Client-side timeout. Increase for slower models to prevent premature timeout errors. |
| `SECBRAIN_EMBEDDING_DIM` | `256` | Output dimension of the embedding model (e.g. 768 for `nomic-embed-text`, 384 for `all-minilm`, 1536 for OpenAI). |
| `SECBRAIN_RETRIEVAL_TOP_K` | `8` (tuned to `4`) | Number of evidence passages passed to the LLM. 4 chunks reduces prompt size by ~50%. |

---

## Changing the Embedding Model (Important)

Embedding vectors are only comparable within the same embedding space. SecBrain
records an **embedding version** (`provider:model:dim`) on every chunk, and
retrieval only scores chunks in the **current** space.

When you change the embedding provider or model, **re-index** affected documents:
1. Go to **Document Library** → open document → click **Reprocess**.
2. Or call `POST /api/v1/documents/{id}/reprocess`.

Documents indexed in an old space will not be returned until reprocessed — they are never silently mixed.

---

## Checking Model Status

Open the **Model Status** page in the web UI, or query:
```bash
curl http://localhost:8000/api/v1/models/status
```
This endpoint checks connectivity, verifies the model is pulled and ready, reports context limits, and confirms the active embedding space without exposing API secrets.
