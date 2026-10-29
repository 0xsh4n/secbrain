# Known Limitations & Security Assumptions

This release delivers a working, secure MVP of the SecBrain knowledge platform.
The following are known limitations, documented honestly.

## Models & retrieval

- **Default providers are offline/deterministic.** The `fake` embedder is a
  hashing embedder (lexically grounded, not semantic) and the `fake` generator
  composes a grounded, citation-shaped response rather than natural language.
  They exist so the platform runs with no GPU/model and so tests/eval are
  reproducible. For real semantic search and natural-language answers, configure
  Ollama or an OpenAI-compatible provider ([LOCAL_MODELS.md](LOCAL_MODELS.md)).
- **Abstention/relevance thresholds are tuned for the default embedder.**
  `SECBRAIN_RETRIEVAL_MIN_LEXICAL` and `…_MIN_COSINE` should be retuned for a
  strong semantic embedding model (and you can enable cosine as a qualifier via
  `SECBRAIN_RETRIEVAL_REQUIRE_LEXICAL_GROUNDING=false`).
- **Changing embedding models requires reprocessing** affected documents so
  their chunks are re-embedded in the new space. Mixed spaces are never silently
  combined — old-space chunks simply aren't returned until reprocessed.
- **No reranker model in the path by default.** An optional cheap lexical rerank
  is provided; a cross-encoder reranker is not included (kept out to avoid heavy
  models on constrained hardware). The hook exists to add one.
- **Token counts are estimated** (~4 chars/token) rather than tokenizer-exact,
  for provider independence.

## Ingestion

- **PDF extraction is text-layer only.** Scanned/image-only PDFs yield no text
  (OCR is not included); such documents fail with a clear error.
- **Social media / paywalled content is not bypassed.** URL ingestion never
  bypasses authentication, paywalls, or CAPTCHAs. For X/Twitter and similar, use
  authorized APIs or paste the text manually. Attribution/original URL is stored.
- **Background processing is in-process** via FastAPI `BackgroundTasks`. It is
  suitable for development and small deployments; for high throughput, move
  ingestion to an external worker (the `services.tasks` functions are designed
  for this) and a queue.

## Scale & operations

- **Default vector store is in-process numpy** over embeddings persisted in the
  primary DB — simple, correct, and durable, but it scores candidate chunks in
  Python. For large corpora, enable Qdrant (`SECBRAIN_VECTOR_STORE=qdrant`),
  which also mirrors vectors on ingestion.
- **Rate limiting is per-process (in-memory).** Multi-replica deployments should
  back it with a shared store (e.g. Redis). The limiter location is isolated in
  `api/deps.py`.
- **Keyword relevance uses candidate-set IDF**, not global corpus statistics;
  this is robust for the shipped use but less precise than a global index at very
  large scale.
- **No built-in horizontal session store / CSRF tokens for cookies** — auth uses
  bearer tokens in the `Authorization` header (not cookies), which avoids CSRF
  for the API surface. If you add cookie auth, add CSRF protection.

## Security assumptions

- The operator sets a strong `SECBRAIN_SECRET_KEY` (≥32 random bytes) and changes
  the bootstrap admin password before exposing the service.
- DB, Qdrant, and model endpoints run on a trusted network; public deployments
  terminate TLS at a fronting proxy.
- `SECBRAIN_ALLOW_PRIVATE_URL_FETCH` must remain `false` in production (it exists
  only for trusted internal test environments).
- Uploaded documents are treated as untrusted data; see
  [THREAT_MODEL.md](THREAT_MODEL.md).

## Voice (Nyx TTS)

- Natural voice uses local **Piper** TTS. The voice model (~63 MB) must be
  downloaded (`python -m app.cli download-voice`); until then the UI falls back
  to browser speech synthesis. Speech recognition (dictation, wake word) relies
  on the browser's service (Chrome/Edge, usually online) and is not provided by
  SecBrain. Streaming TTS synthesizes per sentence, so there can be brief gaps on
  slower CPUs.

## System actions (nmap / app launch)

- **Disabled by default and fail-closed.** When enabled, only a fixed set of
  actions is available (nmap profiles, allowlisted app launch), scoped to
  authorized targets, admin-session only, never LLM/document-triggered, audited.
- App launch runs on the backend host — in a container it launches inside the
  container (no host GUI); it is most useful in the native deployment.
- The scope check reuses the `engagements` model plus a config allowlist. No
  other active testing, exploitation, persistence, or credential handling is
  implemented; any future capability must go through the same fail-closed policy
  layer — authorization is never inferred from a knowledge document.

## Dependencies

- Backend dependencies are pinned and install from prebuilt wheels on Python
  3.12–3.14. Run `pip install pip-audit && pip-audit` to check advisories.
- Frontend: `npm audit` reports **0 vulnerabilities** (Next pinned to a patched
  15.5.x; a `postcss` override is applied to clear a transitive build-time
  advisory). Re-run `npm audit` after dependency changes.

## Tested vs. not tested

- **Tested** (automated): auth, SSRF protections, extraction, chunking,
  ingestion (incl. duplicate detection and embedding-failure handling),
  retrieval (hybrid, exact-id, filters, abstention), authorization/tenant
  isolation, API keys (lifecycle, scope, rate limit), MCP tools, the full
  upload→index→search→answer→delete flow, and the retrieval eval harness.
  Verified manually: live Postgres migrations/bootstrap/retrieval, and the web UI
  login→dashboard→search flow.
- **Not automatically tested**: real third-party model providers (Ollama/OpenAI
  calls are abstracted and covered by deterministic fakes — point the eval
  harness at a real provider to exercise them); Qdrant backend (code path present
  and exercised on upsert/delete/search, but not in the default CI path);
  frontend end-to-end UI automation (the build is type-checked and compiled).
