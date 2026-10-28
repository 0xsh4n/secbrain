# Local Model Configuration

SecBrain is model-independent. Generation and embedding providers are selected
and configured **entirely via environment variables** — no source changes. The
knowledge base (ingestion, search, document management) works with **no model at
all**; a generation model only affects the natural-language answer synthesis in
chat and `/knowledge/answer`.

## Providers

| Variable | Values | Meaning |
|----------|--------|---------|
| `SECBRAIN_LLM_PROVIDER` | `fake` / `ollama` / `openai` | Generation backend |
| `SECBRAIN_EMBEDDING_PROVIDER` | `fake` / `ollama` / `openai` | Embedding backend |

- `fake` — deterministic, offline, no GPU. Default. The embedder is a stable
  hashing embedder; the generator composes a grounded, citation-shaped response
  from the evidence (useful for dev/tests, not for natural language).
- `ollama` — a local [Ollama](https://ollama.com) server.
- `openai` — any OpenAI-compatible `/v1/chat/completions` and `/v1/embeddings`
  endpoint (OpenAI, vLLM, LM Studio, LocalAI, etc.).

## Example: Ollama (local, CPU or small GPU)

```bash
# Start Ollama (or use the compose `models` profile) and pull small models:
ollama pull qwen3:4b              # generation (small, quantized)
ollama pull nomic-embed-text      # embeddings (768-dim)
```

`.env`:

```bash
SECBRAIN_LLM_PROVIDER=ollama
SECBRAIN_LLM_MODEL=qwen3:4b
SECBRAIN_LLM_BASE_URL=http://localhost:11434

SECBRAIN_EMBEDDING_PROVIDER=ollama
SECBRAIN_EMBEDDING_MODEL=nomic-embed-text
SECBRAIN_EMBEDDING_BASE_URL=http://localhost:11434
```

Candidate small models for ≤4 GB VRAM / CPU: `qwen3:4b`, other 3–4B quantized
chat models, or NVIDIA Nemotron small variants **if** they run in your Ollama
runtime. Verify actual fit on your hardware — a model advertised for a 4 GB
workload may not fit every runtime/quantization.

## Example: OpenAI-compatible endpoint

```bash
SECBRAIN_LLM_PROVIDER=openai
SECBRAIN_LLM_MODEL=gpt-4o-mini            # or your server's model id
SECBRAIN_LLM_BASE_URL=https://api.openai.com   # or http://localhost:8001 for vLLM/LM Studio
SECBRAIN_LLM_API_KEY=sk-...

SECBRAIN_EMBEDDING_PROVIDER=openai
SECBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECBRAIN_EMBEDDING_BASE_URL=https://api.openai.com
SECBRAIN_EMBEDDING_API_KEY=sk-...
```

## Tunable model settings (no code changes)

`SECBRAIN_LLM_CONTEXT_TOKENS`, `SECBRAIN_LLM_MAX_OUTPUT_TOKENS`,
`SECBRAIN_LLM_TEMPERATURE`, `SECBRAIN_LLM_TIMEOUT_SECONDS`,
`SECBRAIN_LLM_MAX_CONCURRENCY`, `SECBRAIN_EMBEDDING_DIM`.

## Changing the embedding model (important)

Embedding vectors are only comparable within the same embedding space. SecBrain
records an **embedding version** (`provider:model:dim`) on every chunk, and
retrieval only scores chunks in the **current** space. When you change the
embedding provider/model, **re-index** affected documents (Document detail →
Reprocess, or `POST /documents/{id}/reprocess`) so their chunks are re-embedded
in the new space. Documents indexed in an old space simply won't be returned
until reprocessed — they are never silently mixed.

## Privacy

- `SECBRAIN_DISABLE_OUTBOUND_LLM=true` forces the offline `fake` providers and
  makes no outbound model calls, regardless of other settings.
- The selected provider is visible on the Model Status and Settings pages.
- Document contents are sent to a hosted model only if you explicitly configure
  and authorize an `openai`/`ollama` provider pointing at a remote endpoint.

## Checking status

`GET /api/v1/models/status` (or the **Model Status** page) shows the configured
provider/model, connection health, context limits, and the embedding version —
without exposing any API secrets.

## Model evaluation

`backend/eval/run_eval.py` is a deterministic retrieval/grounding harness
(recall@k, MRR, citation validity, abstention, latency) measured independently of
LLM fluency. Point it at a real provider by exporting the provider env vars
before running `python -m eval.run_eval` to compare retrieval quality and
citation behavior across configurations. Do not judge a model on marketing
claims — measure.
