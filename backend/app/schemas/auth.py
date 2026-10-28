from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _EmailMixin(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v


class LoginRequest(_EmailMixin):
    password: str


class RegisterRequest(_EmailMixin):
    password: str = Field(min_length=8, max_length=200)
    full_name: str = ""
    organization_name: str = Field(default="", max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    organization_id: str
