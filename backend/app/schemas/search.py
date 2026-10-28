from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    collection_ids: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    rerank: bool = False


class EvidenceOut(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    source_url: str
    source_type: str
    text: str
    page_number: int | None
    section_heading: str
    retrieval_method: str
    score: float
    collection_ids: list[str]


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[EvidenceOut]


class AnswerRequest(SearchRequest):
    pass


class ModelInfo(BaseModel):
    name: str
    available: bool


class AnswerResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    query: str
    answer: str
    insufficient_evidence: bool
    cited_labels: list[str]
    evidence: list[EvidenceOut]
    model: ModelInfo
    model_error: str = ""
