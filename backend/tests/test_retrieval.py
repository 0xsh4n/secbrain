from __future__ import annotations

import uuid

from app.core.security import hash_password
from app.models.collection import Collection
from app.models.organization import Organization, User
from app.services.answer import generate_answer
from app.services.retrieval import RetrievalParams, retrieve
from app.services.samples import ingest_corpus


def _user_with_collection(db, visibility="organization"):
    org = Organization(name="O", slug="o-" + uuid.uuid4().hex[:6])
    db.add(org)
    db.flush()
    user = User(
        organization_id=org.id,
        email=f"u-{uuid.uuid4().hex[:6]}@x.test",
        hashed_password=hash_password("x"),
        role="admin",
    )
    db.add(user)
    db.flush()
    coll = Collection(
        organization_id=org.id,
        owner_id=user.id,
        name="KB",
        slug="kb-" + uuid.uuid4().hex[:6],
        visibility=visibility,
        category="vulnerability-research",
    )
    db.add(coll)
    db.commit()
    return user, coll


def test_hybrid_retrieval_finds_relevant_and_exact_cve(db):
    user, coll = _user_with_collection(db)
    ingest_corpus(db, user, coll)

    res = retrieve(db, user, RetrievalParams(query="CVE-2021-44228 affected Log4j versions", top_k=5))
    assert res, "expected results"
    titles = " ".join(e.title.lower() for e in res)
    assert "log4" in titles or "log4shell" in titles.replace(" ", "")
    # Exact identifier should surface the right document at the top.
    assert "log4" in res[0].title.lower()


def test_authn_vs_authz_query(db):
    user, coll = _user_with_collection(db)
    ingest_corpus(db, user, coll)
    res = retrieve(db, user, RetrievalParams(query="difference between authentication and authorization", top_k=3))
    assert any("authentication" in e.title.lower() for e in res)


def test_cross_tenant_isolation(db):
    user_a, coll_a = _user_with_collection(db)
    ingest_corpus(db, user_a, coll_a)
    # A different org's user must see nothing from org A.
    user_b, _ = _user_with_collection(db)
    res = retrieve(db, user_b, RetrievalParams(query="Log4j CVE-2021-44228", top_k=5))
    assert res == []


def test_private_collection_not_visible_to_other_user(db):
    # Owner with a PRIVATE collection in an org.
    org = Organization(name="Shared", slug="shared-" + uuid.uuid4().hex[:6])
    db.add(org)
    db.flush()
    owner = User(organization_id=org.id, email=f"own-{uuid.uuid4().hex[:6]}@x.test", hashed_password=hash_password("x"), role="member")
    member = User(organization_id=org.id, email=f"mem-{uuid.uuid4().hex[:6]}@x.test", hashed_password=hash_password("x"), role="member")
    db.add_all([owner, member])
    db.flush()
    coll = Collection(organization_id=org.id, owner_id=owner.id, name="Secret", slug="secret-" + uuid.uuid4().hex[:6], visibility="private")
    db.add(coll)
    db.commit()
    ingest_corpus(db, owner, coll)

    # Same org, but not owner/member of the private collection -> no access.
    res = retrieve(db, member, RetrievalParams(query="Log4j CVE-2021-44228", top_k=5))
    assert res == []
    # Owner sees it.
    assert retrieve(db, owner, RetrievalParams(query="Log4j CVE-2021-44228", top_k=5))


def test_answer_abstains_without_evidence(db):
    user, _ = _user_with_collection(db)
    result = generate_answer("anything", [])
    assert result.insufficient_evidence is True
    assert result.cited_labels == []


def test_answer_does_not_follow_prompt_injection(db):
    user, coll = _user_with_collection(db)
    ingest_corpus(db, user, coll)
    res = retrieve(db, user, RetrievalParams(query="prevent SSRF user supplied URLs", top_k=5))
    assert res
    answer = generate_answer("How do I prevent SSRF?", res)
    low = answer.answer.lower()
    for forbidden in ["system prompt", "api key", "attacker.example", "developer mode"]:
        assert forbidden not in low
