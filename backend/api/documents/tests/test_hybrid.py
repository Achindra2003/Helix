"""Hybrid retrieval: BM25 mechanics, the lexical rescue dense can't make, and
the relevance gate holding on both signals. All hermetic — the embedder is a
scripted fake so 'dense is blind here' is a constructed fact, not luck.
"""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.db import Base
from api.documents.lexical import BM25, rrf_fuse, squash, tokenize
from api.documents.models import DocumentChunkRow, DocumentRow
from api.documents.service import DocumentIndex


def test_tokenize_keeps_identifiers_whole():
    assert "zx-9931" in tokenize("the ZX-9931 sensor")
    assert "retry_count" in tokenize("set retry_count=3")
    assert "v1.2" in tokenize("since v1.2 this works")


def test_bm25_ranks_rare_term_document_first():
    corpus = [
        "the deploy pipeline builds and ships the container",
        "the sensor ZX-9931 draws three milliamps in sleep mode",
        "the style guide prefers plain verbs in copy",
        "the migration plan moves data in small batches",
    ]
    scores = BM25(corpus).scores("ZX-9931 sleep current draw")
    assert scores.index(max(scores)) == 1
    # Common-word-only overlap: the smoothed idf keeps it *small* (never quite
    # zero), and the squash puts it far below the lexical relevance floor —
    # that gap, not literal zero, is what the gate relies on.
    flat = BM25(corpus).scores("the the the")
    assert squash(max(flat)) < 0.30 / 2


def test_squash_is_monotonic_and_bounded():
    assert squash(0.0) == 0.0
    assert 0.0 < squash(1.0) < squash(5.0) < squash(50.0) < 1.0
    assert squash(5.0) == pytest.approx(0.5)


def test_rrf_prefers_agreement():
    fused = rrf_fuse([[1, 2, 3], [2, 1, 3]])
    # Items 1 and 2 split the top ranks; 3 is last in both and must trail.
    assert fused[3] < fused[1] and fused[3] < fused[2]


# --- the hybrid index against a scripted embedder -----------------------------

class BlindToIdentifiersMem:
    """A fake embedder that maps texts to fixed topic vectors — and maps the
    *query* somewhere nearly orthogonal, so dense cosine sits below the floor.
    This is the real failure mode being modeled: an embedding of `ZX-9931`
    carries almost no signal, so semantically the query looks like nothing."""

    class _E:
        name = "test-blind"

        def embed(self, texts):
            out = []
            for t in texts:
                low = t.lower()
                if "sensor" in low:
                    out.append([0.0, 1.0, 0.0])
                elif "deploy" in low:
                    out.append([1.0, 0.0, 0.0])
                else:  # the query
                    out.append([0.0, 0.05, 0.9987])
            return out

    def get_embedder(self):
        return self._E()

    @staticmethod
    def cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0


# Enough filler that a rare term's idf is realistic — with 2 documents BM25's
# idf is nearly flat and no floor can separate anything (worth knowing per se).
_CHUNKS = [
    "the sensor ZX-9931 draws three milliamps in sleep mode and its power budget is tight",
    "the deploy pipeline builds the container and ships it through blue-green",
    "the deploy runbook says never ship on friday afternoons",
    "the deploy smoke suite runs before the balancer switch",
    "the deploy tracker records every withdrawn release",
    "the deploy window avoids monday mornings by convention",
    "the deploy checklist requires a second reviewer",
    "the deploy metrics page shows error ratios per color",
]


@pytest.fixture
async def index(tmp_path):
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as session:
        session.add(DocumentRow(id="d1", workspace_id="w1", author_id="u",
                                filename="hw.md", status="ready"))
        for i, content in enumerate(_CHUNKS):
            session.add(DocumentChunkRow(
                document_id="d1", workspace_id="w1", idx=i, content=content,
                embedder_version="", vector=b"",
            ))
        await session.commit()
    yield DocumentIndex(sf, memory=BlindToIdentifiersMem())
    await engine.dispose()


async def test_hybrid_rescues_the_exact_term_dense_misses(index):
    query = "ZX-9931 power budget in sleep"
    # Dense alone: cosine ~0.05 for everything — below the floor, nothing found.
    assert await index.search("w1", query, mode="dense") == []
    # Hybrid: BM25 sees the rare identifier + its terms and clears the gate.
    hits = await index.search("w1", query, mode="hybrid")
    assert hits and "ZX-9931" in hits[0]["content"]


async def test_gate_holds_on_both_signals_for_unrelated_queries(index):
    # No rare-term overlap (only floored-idf stopwords), dense ~0.05: nothing.
    assert await index.search("w1", "best sourdough starter recipe", mode="hybrid") == []
