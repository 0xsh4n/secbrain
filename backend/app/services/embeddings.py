"""Embedding provider abstraction.

Providers are swappable via config. The default `fake` provider is a
deterministic, dependency-free hashing embedder: it needs no model, no GPU and
no network, which keeps development and tests fast and reproducible. Real
semantic embeddings come from an Ollama or OpenAI-compatible endpoint.

Every provider exposes `.version` so that documents record the embedding space
they were indexed in; the retrieval layer refuses to mix incompatible spaces.
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

import httpx

from app.config import settings


class EmbeddingProvider(ABC):
    name: str
    model: str
    dim: int

    @property
    def version(self) -> str:
        return f"{self.name}:{self.model}:{self.dim}"

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class FakeHashEmbedding(EmbeddingProvider):
    """Deterministic bag-of-token hashing into a fixed-dim unit vector.

    Not semantically powerful, but stable and offline: identical text always
    yields the identical vector, and lexically similar texts share dimensions,
    which is enough to exercise and test the full retrieval pipeline.
    """

    name = "fake"

    def __init__(self, model: str = "fake-hash-256", dim: int = 256) -> None:
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            tokens = _tokenize(text)
            for tok in tokens:
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 8) & 1 else -1.0
                vec[idx] += sign
            out.append(_l2_normalize(vec))
        return out


def _tokenize(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]+", (text or "").lower())


class OllamaEmbedding(EmbeddingProvider):
    name = "ollama"

    def __init__(self, model: str, base_url: str, dim: int) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            for text in texts:
                resp = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
        if vectors and vectors[0]:
            self.dim = len(vectors[0])
        return vectors


class OpenAICompatibleEmbedding(EmbeddingProvider):
    name = "openai"

    def __init__(self, model: str, base_url: str, api_key: str, dim: int) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            resp = client.post(
                f"{self.base_url}/v1/embeddings",
                headers=headers,
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        vectors = [item["embedding"] for item in data]
        if vectors and vectors[0]:
            self.dim = len(vectors[0])
        return vectors


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is not None:
        return _provider
    p = settings.embedding_provider.lower()
    if p == "ollama" and not settings.disable_outbound_llm:
        _provider = OllamaEmbedding(
            settings.embedding_model, settings.embedding_base_url, settings.embedding_dim
        )
    elif p == "openai" and not settings.disable_outbound_llm:
        _provider = OpenAICompatibleEmbedding(
            settings.embedding_model,
            settings.embedding_base_url,
            settings.embedding_api_key,
            settings.embedding_dim,
        )
    else:
        _provider = FakeHashEmbedding(settings.embedding_model, settings.embedding_dim)
    return _provider


def reset_embedding_provider() -> None:
    """Testing / config-reload hook."""
    global _provider
    _provider = None
