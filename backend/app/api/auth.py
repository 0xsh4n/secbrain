from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.slugs import slugify
from app.db import get_db
from app.models.organization import Organization, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _unique_org_slug(db: Session, name: str) -> str:
    base = slugify(name, "org")
    slug = base
    while db.execute(select(Organization).where(Organization.slug == slug)).scalars().first():
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
    return slug


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == payload.email)).scalars().first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    org_name = payload.organization_name or f"{payload.email.split('@')[0]}'s workspace"
    org = Organization(name=org_name, slug=_unique_org_slug(db, org_name))
    db.add(org)
    db.flush()

    user = User(
        organization_id=org.id,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role="admin",  # first user of a new org administers it
    )
    db.add(user)
    db.commit()
    audit.record(
        db,
        organization_id=org.id,
        action="user.register",
        actor_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=client_ip(request),
    )
    token = create_access_token(user.id, org.id, user.role)
    return TokenResponse(
        access_token=token, expires_in_minutes=settings.access_token_ttl_minutes
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == payload.email)).scalars().first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        # Uniform error (no user enumeration).
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    audit.record(
        db,
        organization_id=user.organization_id,
        action="user.login",
        actor_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=client_ip(request),
    )
    token = create_access_token(user.id, user.organization_id, user.role)
    return TokenResponse(
        access_token=token, expires_in_minutes=settings.access_token_ttl_minutes
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=user.organization_id,
    )
