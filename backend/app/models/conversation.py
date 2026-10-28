"""Chat conversations and messages."""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Conversation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    # JSON array of collection ids scoping retrieval for this conversation.
    collection_ids: Mapped[str] = mapped_column(Text, default="[]")

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    # JSON blob of evidence/citations attached to an assistant message.
    citations: Mapped[str] = mapped_column(Text, default="[]")

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
