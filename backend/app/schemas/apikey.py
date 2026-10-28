from __future__ import annotations

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(default="", max_length=200)
    scoped_collection_ids: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    scoped_collection_ids: list[str]
    rate_limit_per_minute: int
    is_active: bool
    expires_at: str | None
    last_used_at: str | None
    usage_count: int
    created_at: str | None


class ApiKeyCreatedOut(ApiKeyOut):
    # The raw key is returned exactly once, on creation.
    api_key: str
