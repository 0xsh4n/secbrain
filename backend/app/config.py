"""Central configuration for SecBrain.

All runtime behaviour is driven by environment variables so that model
selection, providers, and infrastructure can change without editing source.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SECBRAIN_", extra="ignore"
    )

    # --- Application ---
    app_name: str = "SecBrain"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = True
    # Comma-separated list of allowed CORS origins (frontend).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Security ---
    # MUST be overridden in production. Used to sign JWT session tokens.
    secret_key: str = "dev-insecure-change-me-in-production"
    access_token_ttl_minutes: int = 60 * 12
    # Opt-out switch: when True the app will never make outbound LLM/embedding
    # calls to hosted providers (privacy / air-gapped operation).
    disable_outbound_llm: bool = False

    # --- Database ---
    # SQLite by default (zero-infra dev/test). Postgres via docker-compose.
    database_url: str = "sqlite:///./data/secbrain.db"

    # --- Storage ---
    storage_dir: str = "./data/storage"

    # --- Optional Google Drive knowledge-pool sync ---
    google_drive_client_id: str = ""
    google_drive_client_secret: str = ""
    google_drive_redirect_uri: str = "http://localhost:8000/api/v1/drive-sync/callback"
    google_drive_frontend_url: str = "http://localhost:3000"

    # --- Embeddings provider ---
    # fake | ollama | openai
    embedding_provider: str = "fake"
    embedding_model: str = "fake-hash-256"
    embedding_dim: int = 256
    embedding_base_url: str = "http://localhost:11434"
    embedding_api_key: str = ""

    # --- Generation (LLM) provider ---
    # fake | ollama | openai
    llm_provider: str = "fake"
    llm_model: str = "fake-echo"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_context_tokens: int = 8192
    llm_max_output_tokens: int = 4096
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 120.0
    llm_max_concurrency: int = 2

    # --- Vector store ---
    # memory | qdrant   (memory = in-process numpy over embeddings stored in DB)
    vector_store: str = "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # --- Retrieval defaults ---
    retrieval_top_k: int = 8
    retrieval_min_score: float = 0.0
    # Relevance gating (controls abstention on unsupported questions).
    # A candidate qualifies as evidence if it contains an exact query
    # identifier, OR its IDF-weighted lexical overlap with the query clears
    # `retrieval_min_lexical`, OR (only when `retrieval_require_lexical_grounding`
    # is False) its raw cosine clears `retrieval_min_cosine`. With the default
    # hash embedder cosine is a weak semantic signal, so lexical grounding is
    # required by default; set the flag False when using a strong semantic
    # embedding model and retune `retrieval_min_cosine` accordingly.
    retrieval_require_lexical_grounding: bool = True
    retrieval_min_lexical: float = 0.30
    retrieval_min_cosine: float = 0.30
    retrieval_candidate_multiplier: int = 4  # over-fetch before fusion
    retrieval_max_scan_chunks: int = 5000  # bound per-query memory for local deployments
    chunk_target_tokens: int = 350
    chunk_overlap_tokens: int = 60

    # --- Ingestion / URL fetch safety ---
    max_upload_bytes: int = 25 * 1024 * 1024
    url_fetch_timeout_seconds: float = 15.0
    url_fetch_max_bytes: int = 10 * 1024 * 1024
    url_fetch_max_redirects: int = 3
    allow_private_url_fetch: bool = False  # True only for trusted test environments

    # --- Rate limiting (per API key, requests/minute) ---
    api_rate_limit_per_minute: int = 60

    # --- Bootstrap admin (created on first `init-db` if absent) ---
    bootstrap_admin_email: str = "admin@secbrain.local"
    bootstrap_admin_password: str = "changeme-admin-123"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
