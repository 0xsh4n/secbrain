# SecBrain Threat Model

Scope: the initial release (knowledge platform + REST/MCP integration). Future
active-testing agents are explicitly out of scope and not implemented.

## Assets

- Ingested knowledge (may include confidential pentest reports / client data).
- Per-tenant isolation of documents, collections, conversations, and vectors.
- API keys and user credentials.
- Availability of ingestion/retrieval.

## Trust boundaries

- **Untrusted**: document contents, submitted URLs and the pages they return,
  API/MCP client input. Treated as **data, never instructions**.
- **Trusted**: the application's own code and system prompts, environment
  configuration/secrets.
- Valid instructions come only from the authenticated user/client via the API —
  never from retrieved content.

## Threats and mitigations

### 1. Malicious documents / prompt injection
- Retrieved evidence is wrapped and labeled as untrusted data; the trusted
  system prompt instructs the model to ignore any instructions inside it.
- The generation model is given **no tools**, so injected text cannot cause tool
  execution, secret disclosure, or external calls.
- Covered by tests (`test_retrieval.py::test_answer_does_not_follow_prompt_injection`)
  and the eval harness (`q_injection`, with `must_not_contain` assertions).

### 2. SSRF via URL ingestion
- Only `http`/`https` schemes allowed.
- DNS is resolved and **every** resolved IP is validated against loopback,
  private, link-local (incl. `169.254.169.254` cloud metadata), multicast,
  reserved, and unspecified ranges (IPv4, IPv6, and IPv4-mapped IPv6).
- The connection is **pinned to the validated IP** (TLS SNI still verifies the
  real hostname), mitigating DNS rebinding / TOCTOU.
- Redirects are followed manually and each hop is re-validated; response size,
  time, and content-type are bounded.
- Covered by `test_url_fetcher.py` (scheme rejection, private/metadata/IPv4-mapped
  blocking, hostname→private resolution, pinned-IP fetch, redirect-to-internal,
  content-type rejection).

### 3. Unauthorized retrieval / cross-tenant leakage
- All retrieval and document access resolve the caller's organization first,
  then narrow by collection visibility/membership. An opaque document id never
  implies access.
- Only authorized chunks enter the retrieval candidate set, so evidence cannot
  leak across tenants or private collections.
- API keys may be further scoped to a subset of collections.
- Covered by `test_retrieval.py` (cross-tenant, private-collection),
  `test_api_integration.py` (cross-tenant doc access), and `test_mcp.py`.

### 4. API key compromise
- Keys are generated with a CSPRNG, shown **once**, and stored only as a keyed
  SHA-256 HMAC. Raw keys are never logged.
- Keys support revocation, rotation, expiry, per-key rate limits, and usage
  logging. Admin/web-only operations reject API-key auth.

### 5. Malicious file uploads
- Upload type is restricted by extension to the supported set; size is bounded
  (`max_upload_bytes`). Extraction failures are captured, not fatal to the
  service. Storage keys are sanitized against path traversal.

### 6. Resource exhaustion
- Request size limits, rate limiting (per API key), bounded retrieval candidate
  sets and top-k, and bounded URL fetch size/time.

### 7. Dependency vulnerabilities
- Dependencies are pinned. `pip install` uses prebuilt wheels. Run `pip-audit`
  (backend) and `npm audit` (frontend) as part of quality gates; see
  [LIMITATIONS.md](LIMITATIONS.md) for current known advisories.

### 8. Credential/secret handling
- Passwords hashed with bcrypt; sessions are signed JWTs. Secrets come from
  environment configuration only; none are committed. Internal exceptions are
  caught by a global handler that returns a generic 500 (no tracebacks/secrets
  to clients). Security headers are set on every response.

### 9. System actions (nmap / app launch)
- The action layer is **disabled by default** and **fails closed**. When enabled
  (`SECBRAIN_ACTIONS_ENABLED=true`) it exposes only a fixed, non-free-form set of
  actions: nmap with named profiles, and launching apps from a name→argv
  allowlist.
- **Not LLM-reachable**: execution is driven exclusively by an authenticated
  admin's direct, *structured* request (`POST /actions/execute`). The
  grounded-answer model is given no tools and never calls it, and the command
  parser runs on the user's own utterance — so text inside an ingested document
  can never trigger an action (no prompt-injection → command execution).
- **Scope-gated**: nmap targets must fall within an active, non-expired
  Engagement for the org or an explicit config allowlist; excluded assets and
  anything else are refused. Authorization is never inferred from a domain
  appearing in a knowledge document.
- **No shell**: commands run via argv lists (`shell=False`); nmap flags come from
  fixed profiles; ports are regex-validated; app launches are allowlist-only.
- **Admin session only** (API keys rejected), with every action and refusal
  audit-logged.
- Covered by `test_actions.py` / `test_actions_api.py` (disabled-by-default,
  scope enforcement, exclusions, argument validation, no-shell argv, app
  allowlist, API-key rejection).

### 10. Future agent tools (design-time)
- Beyond the scoped actions above, no automated exploitation, destructive
  testing, persistence, credential theft, or unrestricted scanning is
  implemented. Any future active capability must go through the same policy layer
  (Engagement scope, fail-closed, explicit/time-bounded authorization).

## Assumptions

- The deployment operator sets a strong `SECBRAIN_SECRET_KEY` (≥32 bytes),
  changes the bootstrap admin password, and runs the DB/Qdrant/model services on
  a trusted network.
- The in-process rate limiter is per-process; multi-replica deployments should
  move it to a shared store (documented limitation).
- TLS termination for public deployments is handled by a fronting proxy.
