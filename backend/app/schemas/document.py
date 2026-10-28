from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class TextIngestRequest(BaseModel):
    title: str = Field(default="", max_length=500)
    text: str = Field(min_length=1)
    collection_ids: list[str] = Field(default_factory=list)
    source_type: Literal["text", "markdown"] = "text"


class UrlIngestRequest(BaseModel):
    url: HttpUrl
    title: str = Field(default="", max_length=500)
    collection_ids: list[str] = Field(default_factory=list)
    source_type: Literal["url", "github", "twitter"] = "url"


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    author: str | None = Field(default=None, max_length=300)
    summary: str | None = None
    collection_ids: list[str] | None = None
    tags: list[str] | None = None


class DocumentOut(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: str
    author: str
    status: str
    chunk_count: int
    byte_size: int
    content_hash: str
    is_duplicate: bool
    duplicate_of_id: str | None
    extraction_error: str
    embedding_model: str
    embedding_version: str
    summary: str
    collection_ids: list[str]
    tags: list[str]
    created_at: str | None
    updated_at: str | None


class JobOut(BaseModel):
    id: str
    document_id: str
    state: str
    progress: float
    detail: str
    error: str
    attempts: int
    created_at: str | None
    updated_at: str | None
