"""Documents, chunks, and ingestion jobs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Float, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.collection import document_collections, document_tags
from app.models.mixins import TimestampMixin, UUIDPkMixin

# Ingestion job states (state machine).
JOB_STATES = ("PENDING", "FETCHING", "EXTRACTING", "INDEXING", "COMPLETED", "FAILED", "CANCELLED")
DOC_STATUSES = ("pending", "processing", "indexed", "failed")


class Document(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_org_hash", "organization_id", "content_hash"),
    )

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # pdf | txt | markdown | html | docx | text | url | github | twitter
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), default="")
    author: Mapped[str] = mapped_column(String(300), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Where the raw bytes live (storage backend key), when applicable.
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)

    # Extracted + normalized full text (kept for re-chunking / FTS).
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    # LLM-suggested or user-edited summary / metadata.
    summary: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    extraction_error: Mapped[str] = mapped_column(Text, default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    # Duplicate detection (by content hash within an organization).
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Embedding config version used to index this document's chunks.
    embedding_model: Mapped[str] = mapped_column(String(120), default="")
    embedding_version: Mapped[str] = mapped_column(String(80), default="")

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    collections = relationship("Collection", secondary=document_collections, lazy="selectin")
    tags = relationship("Tag", secondary=document_tags, lazy="selectin")


class Chunk(UUIDPkMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_doc_order", "document_id", "ordinal"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str] = mapped_column(String(500), default="")
    # Embedding stored as JSON array text (portable across sqlite/pg).
    embedding: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(120), default="")

    document: Mapped[Document] = relationship(back_populates="chunks")


class IngestionJob(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[Document] = relationship(back_populates="jobs")
