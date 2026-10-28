"""Authorization: collection access resolution and document read checks.

All retrieval and document access flows through here. Access is always scoped
to the caller's organization first (tenant isolation), then narrowed by
collection visibility / membership. An opaque document id never implies access.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collection import Collection, CollectionMember
from app.models.document import Document
from app.models.organization import User


def accessible_collection_ids(db: Session, user: User) -> set[str]:
    """Collection ids the user may read within their organization."""
    org_id = user.organization_id
    q = select(Collection.id, Collection.owner_id, Collection.visibility).where(
        Collection.organization_id == org_id
    )
    member_ids = set(
        db.execute(
            select(CollectionMember.collection_id).where(CollectionMember.user_id == user.id)
        )
        .scalars()
        .all()
    )
    allowed: set[str] = set()
    for cid, owner_id, visibility in db.execute(q).all():
        if user.is_admin:
            allowed.add(cid)
        elif owner_id == user.id:
            allowed.add(cid)
        elif visibility == "organization":
            allowed.add(cid)
        elif cid in member_ids:
            allowed.add(cid)
    return allowed


def resolve_requested_collections(
    db: Session, user: User, requested: list[str] | None
) -> set[str]:
    """Intersect a requested collection id list with what the user can access.

    ``None`` or empty means "all collections the user can access".
    """
    accessible = accessible_collection_ids(db, user)
    if not requested:
        return accessible
    return {cid for cid in requested if cid in accessible}


def can_read_collection(db: Session, user: User, collection: Collection) -> bool:
    if collection.organization_id != user.organization_id:
        return False
    return collection.id in accessible_collection_ids(db, user)


def can_read_document(db: Session, user: User, document: Document) -> bool:
    if document.organization_id != user.organization_id:
        return False
    if user.is_admin or document.owner_id == user.id:
        return True
    accessible = accessible_collection_ids(db, user)
    doc_collection_ids = {c.id for c in document.collections}
    return bool(doc_collection_ids & accessible)


def can_write_document(db: Session, user: User, document: Document) -> bool:
    if document.organization_id != user.organization_id:
        return False
    return user.is_admin or document.owner_id == user.id
