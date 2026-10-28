from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    visibility: Literal["private", "organization"] = "private"
    category: str = ""


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    visibility: Literal["private", "organization"] | None = None
    category: str | None = None


class CollectionOut(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    visibility: str
    category: str
    owner_id: str
    document_count: int = 0
