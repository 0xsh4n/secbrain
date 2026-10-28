"""Database engine, session management, and declarative base."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {}
    if url.startswith("sqlite"):
        # Needed because FastAPI may use the session across threads.
        connect_args["check_same_thread"] = False
        # Ensure the directory for a file-based sqlite db exists.
        path = url.split("sqlite:///", 1)[-1]
        if path and path not in (":memory:",):
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
