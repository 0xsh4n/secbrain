from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, require_session
from app.core.security import generate_api_key
from app.db import get_db
from app.models.apikey import ApiKey
from app.models.mixins import utcnow
from app.schemas.apikey import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut
from app.schemas.common import iso
from app.services import audit
from app.services.permissions import accessible_collection_ids

router = APIRouter(prefix="/apikeys", tags=["apikeys"])


def _serialize(k: ApiKey) -> ApiKeyOut:
    try:
        scoped = json.loads(k.scoped_collection_ids or "[]")
    except json.JSONDecodeError:
        scoped = []
    return ApiKeyOut(
        id=k.id,
        name=k.name,
        prefix=k.prefix,
        scoped_collection_ids=scoped,
        rate_limit_per_minute=k.rate_limit_per_minute,
        is_active=k.is_active,
        expires_at=iso(k.expires_at),
        last_used_at=iso(k.last_used_at),
        usage_count=k.usage_count,
        created_at=iso(k.created_at),
    )


@router.get("", response_model=list[ApiKeyOut])
def list_keys(db: Session = Depends(get_db), principal: Principal = Depends(require_session)):
    rows = db.execute(
        select(ApiKey).where(ApiKey.user_id == principal.user.id).order_by(ApiKey.created_at.desc())
    ).scalars().all()
    return [_serialize(k) for k in rows]


@router.post("", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
def create_key(
    payload: ApiKeyCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    # Scoped collections must be accessible to the owner.
    accessible = accessible_collection_ids(db, principal.user)
    for cid in payload.scoped_collection_ids:
        if cid not in accessible:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"No access to collection {cid}")
    raw_key, prefix, hashed = generate_api_key()
    expires_at = None
    if payload.expires_in_days:
        expires_at = utcnow() + timedelta(days=payload.expires_in_days)
    key = ApiKey(
        organization_id=principal.user.organization_id,
        user_id=principal.user.id,
        name=payload.name,
        prefix=prefix,
        hashed_key=hashed,
        scoped_collection_ids=json.dumps(payload.scoped_collection_ids),
        rate_limit_per_minute=payload.rate_limit_per_minute,
        expires_at=expires_at,
    )
    db.add(key)
    db.commit()
    audit.record(
        db,
        organization_id=principal.user.organization_id,
        action="apikey.create",
        actor_id=principal.user.id,
        resource_type="api_key",
        resource_id=key.id,
    )
    out = _serialize(key).model_dump()
    # Raw key shown exactly once; never stored or logged.
    return ApiKeyCreatedOut(**out, api_key=raw_key)


@router.post("/{key_id}/rotate", response_model=ApiKeyCreatedOut)
def rotate_key(
    key_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    key = db.get(ApiKey, key_id)
    if key is None or key.user_id != principal.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    raw_key, prefix, hashed = generate_api_key()
    key.prefix = prefix
    key.hashed_key = hashed
    key.is_active = True
    db.add(key)
    db.commit()
    audit.record(
        db,
        organization_id=principal.user.organization_id,
        action="apikey.rotate",
        actor_id=principal.user.id,
        resource_type="api_key",
        resource_id=key.id,
    )
    out = _serialize(key).model_dump()
    return ApiKeyCreatedOut(**out, api_key=raw_key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(
    key_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    key = db.get(ApiKey, key_id)
    if key is None or key.user_id != principal.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    key.is_active = False
    db.add(key)
    db.commit()
    audit.record(
        db,
        organization_id=principal.user.organization_id,
        action="apikey.revoke",
        actor_id=principal.user.id,
        resource_type="api_key",
        resource_id=key.id,
    )
