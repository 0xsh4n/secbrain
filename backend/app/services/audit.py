"""Audit logging helper (minimal, non-sensitive context only)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def record(
    db: Session,
    *,
    organization_id: str,
    action: str,
    actor_type: str = "user",
    actor_id: str = "",
    resource_type: str = "",
    resource_id: str = "",
    detail: str = "",
    ip_address: str = "",
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail[:1000],
            ip_address=ip_address[:64],
        )
    )
    db.commit()
