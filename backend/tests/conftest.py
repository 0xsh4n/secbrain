"""Pytest fixtures. A temp SQLite DB is configured BEFORE the app is imported so
that the module-level engine (and background tasks) use the test database.
"""
from __future__ import annotations

import os
import tempfile

# --- Must run before any `app.*` import ---
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SECBRAIN_DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ["SECBRAIN_STORAGE_DIR"] = tempfile.mkdtemp(prefix="secbrain-storage-")
os.environ["SECBRAIN_ENVIRONMENT"] = "test"
os.environ["SECBRAIN_SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long-000"
os.environ["SECBRAIN_EMBEDDING_PROVIDER"] = "fake"
os.environ["SECBRAIN_LLM_PROVIDER"] = "fake"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    try:
        os.remove(_TMP_DB.name)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _clean_tables(_create_schema):
    """Truncate all tables between tests for isolation."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def _register(client: TestClient, email: str, org: str = "") -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password12345",
            "full_name": email.split("@")[0],
            "organization_name": org or f"{email.split('@')[0]} org",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(client):
    return _register(client, "alice@example.com", "Alice Org")


@pytest.fixture
def other_headers(client):
    return _register(client, "mallory@evil.example", "Mallory Org")
