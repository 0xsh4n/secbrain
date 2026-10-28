from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.search import EvidenceOut


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=300)
    collection_ids: list[str] = Field(default_factory=list)


class ConversationOut(BaseModel):
    id: str
    title: str
    collection_ids: list[str]
    created_at: str | None
    updated_at: str | None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    collection_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=50)
    rerank: bool = False


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[EvidenceOut]
    created_at: str | None
