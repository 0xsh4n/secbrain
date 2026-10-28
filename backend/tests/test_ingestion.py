from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.document import Chunk, Document, IngestionJob
from app.models.organization import Organization, User
from app.core.security import hash_password
from app.services import ingestion
from app.services.ingestion import process_document


def _make_user(db) -> User:
    org = Organization(name="Org", slug="org-" + __import__("uuid").uuid4().hex[:6])
    db.add(org)
    db.flush()
    user = User(
        organization_id=org.id,
        email=f"u-{__import__('uuid').uuid4().hex[:6]}@x.test",
        hashed_password=hash_password("x"),
        role="admin",
    )
    db.add(user)
    db.commit()
    return user


def _text_doc(db, user, text="SQL injection and XSS in web apps. CVE-2021-44228 affects Log4j."):
    doc = Document(
        organization_id=user.organization_id,
        owner_id=user.id,
        title="Doc",
        source_type="text",
        extracted_text=text,
        status="pending",
    )
    db.add(doc)
    db.flush()
    db.add(IngestionJob(organization_id=user.organization_id, document_id=doc.id))
    db.commit()
    return doc


def test_process_text_document_indexes(db):
    user = _make_user(db)
    doc = _text_doc(db, user)
    process_document(db, doc.id)
    db.refresh(doc)
    assert doc.status == "indexed"
    assert doc.chunk_count >= 1
    assert doc.content_hash
    chunks = db.execute(select(Chunk).where(Chunk.document_id == doc.id)).scalars().all()
    assert len(chunks) == doc.chunk_count
    assert all(c.embedding for c in chunks)
    job = db.execute(select(IngestionJob).where(IngestionJob.document_id == doc.id)).scalars().first()
    assert job.state == "COMPLETED"


def test_duplicate_detection(db):
    user = _make_user(db)
    d1 = _text_doc(db, user, "identical content about kerberos and NTLM relay")
    process_document(db, d1.id)
    d2 = _text_doc(db, user, "identical content about kerberos and NTLM relay")
    process_document(db, d2.id)
    db.refresh(d2)
    assert d2.is_duplicate is True
    assert d2.duplicate_of_id == d1.id
    assert d2.chunk_count == 0


def test_embedding_failure_marks_failed(db, monkeypatch):
    user = _make_user(db)
    doc = _text_doc(db, user)

    class Boom:
        version = "boom:boom:1"
        model = "boom"

        def embed(self, texts):
            raise RuntimeError("embedding backend down")

    monkeypatch.setattr(ingestion, "get_embedding_provider", lambda: Boom())
    process_document(db, doc.id)
    db.refresh(doc)
    assert doc.status == "failed"
    job = db.execute(select(IngestionJob).where(IngestionJob.document_id == doc.id)).scalars().first()
    assert job.state == "FAILED"
    assert "embedding backend down" in job.error


def test_empty_extraction_fails(db):
    user = _make_user(db)
    doc = _text_doc(db, user, text="   ")
    process_document(db, doc.id)
    db.refresh(doc)
    assert doc.status == "failed"
