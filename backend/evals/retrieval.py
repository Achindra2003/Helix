"""Retrieval evals: is the RAG actually finding the right things?

Wiring retrieval is easy; *measuring* it is what separates a demo from an
engineered system. This harness runs the golden set (retrieval-golden.json —
labeled queries over a realistic team knowledge base) against each retrieval
arm and reports:

    recall@1 / recall@k   did a relevant document make the top / the top-k?
    MRR                   how high did the first relevant document rank?
    negative leakage      did any unrelated query retrieve ANYTHING? (the
                          relevance gate's promise is zero)

Arms:
    dense    cosine over the shared embedder (the pre-hybrid behaviour)
    lexical  BM25 only (api/documents/lexical.py)
    hybrid   both, RRF-fused, either floor admits (the production default)

Judgments are document-level (a retrieved chunk counts if its document is
relevant) so re-chunking doesn't invalidate labels. Ingestion goes through the
production chunker; vectors come from whatever embedder the environment has
(MiniLM when installed/cached, the engine's lexical fallback otherwise) — the
report says which, because dense numbers are only comparable within one
embedder.

Run (from backend/):  python -m evals.retrieval
Hermetic self-test:   pytest evals/test_retrieval_hermetic.py
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

GOLDEN = Path(__file__).parent / "retrieval-golden.json"
RESULTS_DIR = Path(__file__).parent / "results"

ARMS = ("dense", "lexical", "hybrid")


@dataclass
class ArmReport:
    arm: str
    recall_at_1: float
    recall_at_k: float
    mrr: float
    negative_leakage: float
    k: int
    per_query: list[dict] = field(default_factory=list)


async def build_index(documents: list[dict], *, memory=None):
    """A scratch DocumentIndex over an in-memory DB, ingested through the
    production chunker. Vectors are left empty — the index's lazy re-embed
    path (`_current_vectors`) fills them on first search, exactly as an
    embedder upgrade would in production."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from api.db import Base
    from api.documents.models import DocumentChunkRow, DocumentRow
    from api.documents.service import DocumentIndex, chunk_text

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    chunk_to_doc: dict[str, str] = {}
    async with sf() as session:
        for doc in documents:
            session.add(
                DocumentRow(
                    id=doc["id"], workspace_id="golden", author_id="eval",
                    filename=doc["filename"], status="ready",
                )
            )
            for idx, chunk in enumerate(chunk_text(doc["text"])):
                session.add(
                    DocumentChunkRow(
                        document_id=doc["id"], workspace_id="golden", idx=idx,
                        content=chunk, embedder_version="", vector=b"",
                    )
                )
        await session.commit()

    index = DocumentIndex(sf, memory=memory)
    return index, engine


async def evaluate_arm(index, queries: list[dict], *, arm: str, k: int = 4) -> ArmReport:
    positives = [q for q in queries if q["relevant"]]
    negatives = [q for q in queries if not q["relevant"]]

    hits_at_1 = hits_at_k = 0
    rr_sum = 0.0
    per_query: list[dict] = []
    for q in positives:
        results = await index.search("golden", q["text"], k=k, mode=arm)
        got_docs = [r["document_id"] for r in results]
        relevant = set(q["relevant"])
        first_rank = next(
            (i + 1 for i, d in enumerate(got_docs) if d in relevant), None
        )
        hits_at_1 += 1 if first_rank == 1 else 0
        hits_at_k += 1 if first_rank is not None else 0
        rr_sum += (1.0 / first_rank) if first_rank else 0.0
        per_query.append(
            {"id": q["id"], "kind": q["kind"], "got": got_docs, "first_rank": first_rank}
        )

    leaked = 0
    for q in negatives:
        results = await index.search("golden", q["text"], k=k, mode=arm)
        if results:
            leaked += 1
        per_query.append(
            {"id": q["id"], "kind": q["kind"],
             "got": [r["document_id"] for r in results], "first_rank": None}
        )

    n_pos = max(1, len(positives))
    return ArmReport(
        arm=arm,
        recall_at_1=hits_at_1 / n_pos,
        recall_at_k=hits_at_k / n_pos,
        mrr=rr_sum / n_pos,
        negative_leakage=leaked / max(1, len(negatives)),
        k=k,
        per_query=per_query,
    )


async def run_all(*, memory=None, k: int = 4) -> tuple[list[ArmReport], str]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    index, engine = await build_index(data["documents"], memory=memory)
    try:
        embedder = index.version
        reports = [
            await evaluate_arm(index, data["queries"], arm=arm, k=k) for arm in ARMS
        ]
        return reports, embedder
    finally:
        await engine.dispose()


def render_report(reports: list[ArmReport], embedder: str) -> str:
    lines = [
        f"# Retrieval eval — {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Embedder: `{embedder}` · golden set: {GOLDEN.name}",
        "",
        "| arm | recall@1 | recall@k | MRR | negative leakage |",
        "|-----|----------|----------|-----|------------------|",
    ]
    for r in reports:
        lines.append(
            f"| {r.arm} | {r.recall_at_1:.2f} | {r.recall_at_k:.2f} "
            f"| {r.mrr:.2f} | {r.negative_leakage:.2f} |"
        )
    lines.append("")
    lines.append("Per-query misses (first relevant not at rank 1):")
    for r in reports:
        misses = [p for p in r.per_query if p["first_rank"] not in (1, None)]
        wrong = [p for p in r.per_query if p["first_rank"] is None and p["kind"] != "negative"]
        leaks = [p for p in r.per_query if p["kind"] == "negative" and p["got"]]
        for p in misses:
            lines.append(f"- {r.arm} · {p['id']} ({p['kind']}): rank {p['first_rank']} — got {p['got']}")
        for p in wrong:
            lines.append(f"- {r.arm} · {p['id']} ({p['kind']}): MISSED — got {p['got']}")
        for p in leaks:
            lines.append(f"- {r.arm} · {p['id']}: LEAKED — got {p['got']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    reports, embedder = asyncio.run(run_all())
    report = render_report(reports, embedder)
    print(report)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"retrieval-{time.strftime('%Y%m%d-%H%M%S')}.md"
    out.write_text(report, encoding="utf-8")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
