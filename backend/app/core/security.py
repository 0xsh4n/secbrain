"""Password hashing, JWT session tokens, and API key generation/hashing."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

API_KEY_PREFIX = "sk_secbrain_"
_JWT_ALG = "HS256"


# --- Passwords ---------------------------------------------------------------
def _pw_bytes(password: str) -> bytes:
    # bcrypt only considers the first 72 bytes; truncate explicitly so inputs
    # longer than that do not raise (bcrypt>=5 errors instead of truncating).
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), hashed.encode("ascii"))
    except Exception:
        return False


# --- JWT session tokens ------------------------------------------------------
def create_access_token(user_id: str, org_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org": org_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALG)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALG])


# --- API keys ----------------------------------------------------------------
def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, prefix, hashed_key).

    The raw key is shown to the user exactly once. Only the hash is stored.
    """
    raw_secret = secrets.token_urlsafe(32)
    raw_key = f"{API_KEY_PREFIX}{raw_secret}"
    prefix = raw_key[: len(API_KEY_PREFIX) + 6]
    return raw_key, prefix, hash_api_key(raw_key)


def hash_api_key(raw_key: str) -> str:
    """Deterministic keyed hash for lookup. Not reversible."""
    return hmac.new(
        settings.secret_key.encode(), raw_key.encode(), hashlib.sha256
    ).hexdigest()


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), hashed_key)
