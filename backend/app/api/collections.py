from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_user, get_principal, require_session
from app.core.slugs import slugify
from app.core.taxonomy import SECURITY_CATEGORIES
from app.db import get_db
from app.models.collection import Collection, document_collections
from app.models.organization import User
from app.schemas.collection import CollectionCreate, CollectionOut, CollectionUpdate
from app.services.permissions import accessible_collection_ids, can_read_collection

router = APIRouter(prefix="/collections", tags=["collections"])


def _doc_count(db: Session, collection_id: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(document_collections)
        .where(document_collections.c.collection_id == collection_id)
    ).scalar_one()


def _serialize(db: Session, c: Collection) -> CollectionOut:
    return CollectionOut(
        id=c.id,
        name=c.name,
        slug=c.slug,
        description=c.description,
        visibility=c.visibility,
        category=c.category,
        owner_id=c.owner_id,
        document_count=_doc_count(db, c.id),
    )


@router.get("/categories")
def list_categories() -> dict:
    return {"categories": SECURITY_CATEGORIES}


@router.get("", response_model=list[CollectionOut])
def list_collections(
    db: Session = Depends(get_db), principal: Principal = Depends(get_principal)
):
    user = principal.user
    allowed = accessible_collection_ids(db, user)
    # API keys may be scoped to a subset of collections.
    if principal.is_api and principal.scoped_collection_ids:
        allowed &= set(principal.scoped_collection_ids)
    if not allowed:
        return []
    rows = db.execute(select(Collection).where(Collection.id.in_(allowed))).scalars().all()
    return [_serialize(db, c) for c in rows]


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CollectionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    user = principal.user
    if payload.category and payload.category not in SECURITY_CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown security category")
    base_slug = slugify(payload.name, "collection")
    slug = base_slug
    while db.execute(
        select(Collection).where(
            Collection.organization_id == user.organization_id, Collection.slug == slug
        )
    ).scalars().first():
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
    c = Collection(
        organization_id=user.organization_id,
        owner_id=user.id,
        name=payload.name,
        slug=slug,
        description=payload.description,
        visibility=payload.visibility,
        category=payload.category,
    )
    db.add(c)
    db.commit()
    return _serialize(db, c)


def _get_owned_or_404(db: Session, user: User, collection_id: str) -> Collection:
    c = db.get(Collection, collection_id)
    if c is None or c.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    return c


@router.get("/{collection_id}", response_model=CollectionOut)
def get_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    c = _get_owned_or_404(db, principal.user, collection_id)
    if not can_read_collection(db, principal.user, c):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    if principal.is_api and principal.scoped_collection_ids and c.id not in principal.scoped_collection_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    return _serialize(db, c)


@router.patch("/{collection_id}", response_model=CollectionOut)
def update_collection(
    collection_id: str,
    payload: CollectionUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    c = _get_owned_or_404(db, principal.user, collection_id)
    if not (principal.user.is_admin or c.owner_id == principal.user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to modify this collection")
    if payload.category and payload.category not in SECURITY_CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown security category")
    for field_name in ("name", "description", "visibility", "category"):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(c, field_name, value)
    db.add(c)
    db.commit()
    return _serialize(db, c)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    c = _get_owned_or_404(db, principal.user, collection_id)
    if not (principal.user.is_admin or c.owner_id == principal.user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to delete this collection")
    # Documents are not deleted; they are unlinked from this collection.
    db.execute(
        document_collections.delete().where(
            document_collections.c.collection_id == collection_id
        )
    )
    db.delete(c)
    db.commit()
