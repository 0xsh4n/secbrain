"""Seed synthetic sample documents (also used as the eval corpus)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.slugs import slugify
from app.db import SessionLocal
from app.models.collection import Collection
from app.models.document import Document, IngestionJob
from app.models.organization import User
from app.services.ingestion import process_document

CORPUS_DIR = Path(__file__).resolve().parents[2] / "eval" / "dataset" / "corpus"


def ingest_corpus(
    db: Session, user: User, collection: Collection | None, corpus_dir: Path = CORPUS_DIR
) -> dict[str, str]:
    """Ingest every corpus file as a markdown document for ``user``.

    Returns a mapping of corpus-file stem -> document id. Runs the pipeline
    synchronously (used by the CLI seeder and the evaluation harness).
    """
    mapping: dict[str, str] = {}
    for path in sorted(corpus_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
        doc = Document(
            organization_id=user.organization_id,
            owner_id=user.id,
            title=title,
            source_type="markdown",
            extracted_text=text,
            status="pending",
        )
        if collection is not None:
            doc.collections = [collection]
        db.add(doc)
        db.flush()
        db.add(IngestionJob(organization_id=user.organization_id, document_id=doc.id))
        db.commit()
        process_document(db, doc.id)
        mapping[path.stem] = doc.id
    return mapping


def seed_sample_documents() -> int:
    """CLI entry: ingest samples into the bootstrap admin's first collection."""
    db = SessionLocal()
    try:
        admin = db.execute(
            select(User).where(User.email.like("%admin%")).order_by(User.created_at.asc())
        ).scalars().first()
        if admin is None:
            raise RuntimeError("No admin user found. Run `python -m app.cli bootstrap` first.")
        collection = db.execute(
            select(Collection).where(Collection.organization_id == admin.organization_id)
        ).scalars().first()
        if collection is None:
            collection = Collection(
                organization_id=admin.organization_id,
                owner_id=admin.id,
                name="Sample Knowledge",
                slug=slugify("Sample Knowledge"),
                visibility="organization",
                category="vulnerability-research",
            )
            db.add(collection)
            db.commit()
        return len(ingest_corpus(db, admin, collection))
    finally:
        db.close()
