"""Collections, their membership, and tags."""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Table, Column, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin

# Many-to-many: documents <-> collections
document_collections = Table(
    "document_collections",
    Base.metadata,
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("collection_id", ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-many: documents <-> tags
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Collection(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_collection_org_slug"),)

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")
    # "private" (owner + explicit members) | "organization" (all org users)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)
    # Security domain category (see app.core.taxonomy)
    category: Mapped[str] = mapped_column(String(60), default="", nullable=False)

    members: Mapped[list["CollectionMember"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class CollectionMember(UUIDPkMixin, TimestampMixin, Base):
    """Explicit per-user access grant to a private collection."""

    __tablename__ = "collection_members"
    __table_args__ = (
        UniqueConstraint("collection_id", "user_id", name="uq_collection_member"),
    )

    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # "read" | "write"
    access: Mapped[str] = mapped_column(String(20), default="read", nullable=False)

    collection: Mapped[Collection] = relationship(back_populates="members")


class Tag(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_tag_org_name"),)

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
