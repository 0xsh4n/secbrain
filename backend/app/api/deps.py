"""Shared FastAPI dependencies: auth principals and rate limiting.

Two authentication paths yield a common ``Principal`` object:
  * Bearer JWT  -> interactive web user.
  * X-API-Key   -> external AI integration (scoped, rate-limited, logged).
Both resolve to a concrete ``User`` so the same authorization logic applies.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_api_key
from app.db import get_db
from app.models.apikey import ApiKey
from app.models.mixins import utcnow
from app.models.organization import User


@dataclass
class Principal:
    user: User
    auth_type: str  # "session" | "api_key"
    api_key: ApiKey | None = None
    scoped_collection_ids: list[str] = field(default_factory=list)

    @property
    def is_api(self) -> bool:
        return self.auth_type == "api_key"


def _user_from_bearer(authorization: str | None, db: Session) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


# Simple in-process fixed-window rate limiter for API keys. For multi-process
# deployments this should move to Redis; documented as a known limitation.
_rate_state: dict[str, tuple[int, float]] = {}


def _check_rate_limit(key_id: str, limit_per_minute: int) -> None:
    now = time.time()
    window = int(now // 60)
    count, w = _rate_state.get(key_id, (0, window))
    if w != window:
        count, w = 0, window
    count += 1
    _rate_state[key_id] = (count, w)
    if count > max(1, limit_per_minute):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded for this API key"
        )


def _principal_from_api_key(raw_key: str, db: Session) -> Principal:
    hashed = hash_api_key(raw_key)
    key = db.execute(select(ApiKey).where(ApiKey.hashed_key == hashed)).scalars().first()
    if key is None or not key.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    if key.expires_at is not None and key.expires_at < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key expired")
    _check_rate_limit(key.id, key.rate_limit_per_minute)
    user = db.get(User, key.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Owning user inactive")
    # Record usage (no raw key is ever stored or logged).
    key.last_used_at = utcnow()
    key.usage_count += 1
    db.add(key)
    db.commit()
    try:
        scoped = json.loads(key.scoped_collection_ids or "[]")
    except json.JSONDecodeError:
        scoped = []
    return Principal(user=user, auth_type="api_key", api_key=key, scoped_collection_ids=scoped)


def get_principal(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> Principal:
    if x_api_key:
        return _principal_from_api_key(x_api_key.strip(), db)
    user = _user_from_bearer(authorization, db)
    if user is not None:
        return Principal(user=user, auth_type="session")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


def get_current_user(principal: Principal = Depends(get_principal)) -> User:
    return principal.user


def require_session(principal: Principal = Depends(get_principal)) -> Principal:
    """Endpoints that must not be reachable with an API key (admin/web only)."""
    if principal.auth_type != "session":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This operation requires an interactive session"
        )
    return principal


def require_admin(principal: Principal = Depends(require_session)) -> Principal:
    if not principal.user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return principal


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
