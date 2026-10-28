"""Management CLI: initialize the database, bootstrap an admin, seed data.

Usage (from backend/ with the venv active):
    python -m app.cli init-db          # create tables (dev; prefer alembic in prod)
    python -m app.cli bootstrap        # create the bootstrap admin + default collections
    python -m app.cli seed-samples      # ingest the sample synthetic documents
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.core.slugs import slugify
from app.db import Base, SessionLocal, engine
from app.models.collection import Collection
from app.models.organization import Organization, User


def init_db() -> None:
    import app.models  # noqa: F401 ensure metadata is populated

    Base.metadata.create_all(bind=engine)
    print(f"[init-db] tables created on {settings.database_url}")


def bootstrap() -> None:
    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.email == settings.bootstrap_admin_email)
        ).scalars().first()
        if existing:
            print(f"[bootstrap] admin already exists: {existing.email}")
            return
        org = Organization(name="SecBrain", slug="secbrain")
        db.add(org)
        db.flush()
        admin = User(
            organization_id=org.id,
            email=settings.bootstrap_admin_email,
            full_name="SecBrain Admin",
            hashed_password=hash_password(settings.bootstrap_admin_password),
            role="admin",
        )
        db.add(admin)
        db.flush()
        for name, category in [
            ("Web Application Security", "web-application-security"),
            ("API Security", "api-security"),
            ("Vulnerability Research", "vulnerability-research"),
        ]:
            db.add(
                Collection(
                    organization_id=org.id,
                    owner_id=admin.id,
                    name=name,
                    slug=slugify(name),
                    visibility="organization",
                    category=category,
                )
            )
        db.commit()
        print(f"[bootstrap] created org 'SecBrain' and admin {admin.email}")
        print("[bootstrap] NOTE: change the bootstrap admin password immediately.")
    finally:
        db.close()


def seed_samples() -> None:
    from app.services.samples import seed_sample_documents

    count = seed_sample_documents()
    print(f"[seed-samples] ingested {count} sample documents")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "init-db":
        init_db()
    elif cmd == "bootstrap":
        init_db()
        bootstrap()
    elif cmd == "seed-samples":
        seed_samples()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
