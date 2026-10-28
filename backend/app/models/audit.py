"""Audit log and the conceptual engagement (future authorized-testing) model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class AuditLog(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), default="user")  # user | api_key | system
    actor_id: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(60), default="")
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    # Minimal, non-sensitive context only (never raw secrets or doc contents).
    detail: Mapped[str] = mapped_column(Text, default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")


class Engagement(UUIDPkMixin, TimestampMixin, Base):
    """Conceptual authorization model for FUTURE active security testing.

    No active testing is implemented in this release. This table records the
    scope/authorization envelope that a future agent policy layer must check,
    and is designed to *fail closed* (authorization defaults to pending).
    """

    __tablename__ = "engagements"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # JSON arrays of scope definitions.
    authorized_assets: Mapped[str] = mapped_column(Text, default="[]")
    allowed_domains: Mapped[str] = mapped_column(Text, default="[]")
    allowed_ip_ranges: Mapped[str] = mapped_column(Text, default="[]")
    excluded_assets: Mapped[str] = mapped_column(Text, default="[]")
    permitted_methods: Mapped[str] = mapped_column(Text, default="[]")
    prohibited_actions: Mapped[str] = mapped_column(Text, default="[]")
    testing_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    testing_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_rate_limit: Mapped[int] = mapped_column(Integer, default=0)
    # pending | authorized | expired | revoked  (defaults to pending => fail closed)
    authorization_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_history: Mapped[str] = mapped_column(Text, default="[]")
