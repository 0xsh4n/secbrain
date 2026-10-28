"""Retrieval + grounding evaluation harness.

Seeds the synthetic corpus into a throwaway SQLite database, runs the real
retrieval pipeline for each question in ``dataset/questions.json`` and reports
deterministic metrics that are independent of language-model fluency:

  * Recall@k           - did the relevant document(s) appear in the top k?
  * MRR                - mean reciprocal rank of the first relevant document.
  * Citation validity  - do returned evidence citations point to real chunks?
  * Abstention         - does the system abstain when no evidence exists?
  * Latency            - per-query retrieval latency (ms).

Run (from backend/, venv active):
    python -m eval.run_eval
Exit code is non-zero if any hard assertion fails, so it can gate CI.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Isolated DB before importing the app.
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
os.environ.setdefault("SECBRAIN_DATABASE_URL", f"sqlite:///{_TMP.name}")
os.environ.setdefault("SECBRAIN_EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("SECBRAIN_LLM_PROVIDER", "fake")

from app.core.security import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.models.collection import Collection  # noqa: E402
from app.models.document import Chunk  # noqa: E402
from app.models.organization import Organization, User  # noqa: E402
from app.services.answer import generate_answer  # noqa: E402
from app.services.retrieval import RetrievalParams, retrieve  # noqa: E402
from app.services.samples import ingest_corpus  # noqa: E402

DATASET = Path(__file__).resolve().parent / "dataset" / "questions.json"
TOP_K = 5


def _setup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    org = Organization(name="Eval", slug="eval-" + uuid.uuid4().hex[:6])
    db.add(org)
    db.flush()
    user = User(
        organization_id=org.id,
        email=f"eval-{uuid.uuid4().hex[:6]}@x.test",
        hashed_password=hash_password("x"),
        role="admin",
    )
    db.add(user)
    db.flush()
    coll = Collection(
        organization_id=org.id, owner_id=user.id, name="Eval KB",
        slug="eval-kb-" + uuid.uuid4().hex[:6], visibility="organization",
        category="vulnerability-research",
    )
    db.add(coll)
    db.commit()
    mapping = ingest_corpus(db, user, coll)
    return db, user, mapping


def main() -> int:
    db, user, mapping = _setup()
    questions = json.loads(DATASET.read_text())

    recall_hits = 0
    recall_total = 0
    rr_sum = 0.0
    citation_checks = 0
    citation_valid = 0
    abstain_total = 0
    abstain_correct = 0
    latencies: list[float] = []
    failures: list[str] = []

    print(f"\nSecBrain retrieval evaluation  (corpus={len(mapping)} docs, k={TOP_K})\n" + "-" * 72)
    for q in questions:
        expected_ids = {mapping[s] for s in q.get("relevant", []) if s in mapping}
        t0 = time.perf_counter()
        results = retrieve(db, user, RetrievalParams(query=q["query"], top_k=TOP_K))
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        returned_ids = [e.document_id for e in results]

        # Citation validity: every returned chunk id must exist in the DB.
        for e in results:
            citation_checks += 1
            if db.get(Chunk, e.chunk_id) is not None:
                citation_valid += 1

        rank = None
        if expected_ids:
            recall_total += 1
            for i, did in enumerate(returned_ids, start=1):
                if did in expected_ids:
                    rank = i
                    break
            if rank is not None:
                recall_hits += 1
                rr_sum += 1.0 / rank

        # Abstention behaviour.
        status = "ok"
        if q.get("expect_abstain"):
            abstain_total += 1
            ans = generate_answer(q["query"], results)
            if ans.insufficient_evidence:
                abstain_correct += 1
            else:
                status = "FAIL(no-abstain)"
                failures.append(f"{q['id']}: expected abstention but answered")
        elif expected_ids and rank is None:
            status = "FAIL(miss)"
            failures.append(f"{q['id']}: relevant doc not in top {TOP_K}")

        # Prompt-injection safety check.
        if q.get("must_not_contain"):
            ans = generate_answer(q["query"], results)
            low = ans.answer.lower()
            leaked = [t for t in q["must_not_contain"] if t.lower() in low]
            if leaked:
                status = "FAIL(injection-leak)"
                failures.append(f"{q['id']}: leaked {leaked}")

        rank_str = f"rank={rank}" if rank else ("abstain" if q.get("expect_abstain") else "rank=-")
        print(f"  [{status:18}] {q['id']:22} {rank_str:10} {latency_ms:6.1f}ms  {q['type']}")

    db.close()

    recall = recall_hits / recall_total if recall_total else 0.0
    mrr = rr_sum / recall_total if recall_total else 0.0
    cite = citation_valid / citation_checks if citation_checks else 1.0
    abstain = abstain_correct / abstain_total if abstain_total else 1.0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

    print("-" * 72)
    print(f"  Recall@{TOP_K}:          {recall:.3f}  ({recall_hits}/{recall_total})")
    print(f"  MRR:                {mrr:.3f}")
    print(f"  Citation validity:  {cite:.3f}  ({citation_valid}/{citation_checks})")
    print(f"  Abstention correct: {abstain:.3f}  ({abstain_correct}/{abstain_total})")
    print(f"  Avg latency:        {avg_lat:.1f} ms")
    print("-" * 72)

    try:
        os.remove(_TMP.name)
    except OSError:
        pass

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    # Hard gates for CI.
    if recall < 0.9 or cite < 1.0 or abstain < 1.0:
        print("\nGATE FAILED: recall<0.9 or citation<1.0 or abstention<1.0")
        return 1
    print("\nAll evaluation gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
