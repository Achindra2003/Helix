"""Persisted retrieval substrate: embed-once rows, version-aware re-embeds,
persisted-vector recall, and the producer seam that consumes it.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select

from api.db import Base
from api.conversation.embeddings import EmbeddingIndex, NodeEmbeddingRow, _pack
from api.conversation.events import Node, Token
from api.conversation.context import build_messages
from api.conversation.producer import ChatProducer


class CountingEmbedder:
    """Deterministic 4-dim 'embedder' that counts embed calls: similarity is
    driven by which of four keyword buckets a text hits."""

    name = "counting-test-embedder"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        out = []
        for t in texts:
            t = t.lower()
            vec = [
                1.0 if "retry" in t else 0.0,
                1.0 if "filler" in t else 0.0,
                1.0 if "deploy" in t else 0.0,
                0.1,
            ]
            norm = sum(v * v for v in vec) ** 0.5
            out.append([v / norm for v in vec])
        return out


class FakeMemory:
    """Stands in for the engine's memory module (get_embedder + cosine)."""

    def __init__(self, embedder):
        self._embedder = embedder

    def get_embedder(self):
        return self._embedder

    @staticmethod
    def cosine_similarity(a, b):
        return sum(x * y for x, y in zip(a, b))


@pytest_asyncio.fixture
async def sf(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/emb.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _node(i, content, role="user"):
    return Node(
        id=f"n{i}", branch_id="b1", parent_id=None, seq=i,
        role=role, content=content, author_id="alice",
    )


def _index(sf):
    embedder = CountingEmbedder()
    return EmbeddingIndex(sf, memory=FakeMemory(embedder)), embedder


@pytest.mark.asyncio
async def test_ensure_persists_once_and_is_idempotent(sf):
    index, embedder = _index(sf)
    nodes = [_node(1, "we retry three times"), _node(2, "deploy on friday")]

    await index.ensure(nodes)
    assert embedder.calls == 1  # one batched embed for both

    await index.ensure(nodes)
    assert embedder.calls == 1  # second call: pure cache hit, zero embeds

    vecs = await index.vectors(["n1", "n2"])
    assert set(vecs) == {"n1", "n2"}
    assert len(vecs["n1"]) == 4  # unpacked to the embedder's dimension


@pytest.mark.asyncio
async def test_version_mismatch_re_embeds_in_place(sf):
    index, embedder = _index(sf)
    node = _node(1, "we retry three times")

    # A row from an older embedder version…
    async with sf() as session:
        session.add(
            NodeEmbeddingRow(node_id="n1", version="old-embedder", vector=_pack([9.0]))
        )
        await session.commit()

    # …is invisible to current-version reads, and ensure() overwrites it.
    assert await index.vectors(["n1"]) == {}
    await index.ensure([node])
    vecs = await index.vectors(["n1"])
    assert len(vecs["n1"]) == 4  # re-embedded under the current version

    async with sf() as session:
        rows = (await session.execute(select(NodeEmbeddingRow))).scalars().all()
    assert len(rows) == 1  # overwritten, not duplicated


@pytest.mark.asyncio
async def test_rank_returns_relevant_nodes_chronologically(sf):
    index, _ = _index(sf)
    nodes = [
        _node(1, "we agreed to retry exactly three times"),
        _node(2, "filler chatter about nothing"),
        _node(3, "another retry policy note"),
    ]
    picks = await index.rank("how many retry attempts?", nodes, k=2)
    assert [n.id for n in picks] == ["n1", "n3"]  # relevant only, in thread order


@pytest.mark.asyncio
async def test_recall_block_quotes_the_relevant_elided_turn(sf):
    index, _ = _index(sf)
    early = _node(0, "decision: retry exactly three times")
    filler = [_node(i, f"filler {i} " + "z " * 4000) for i in range(1, 9)]
    question = _node(9, "remind me the retry count?")
    history = [early, *filler, question]

    block = await index.recall_block(history)
    assert "retry exactly three times" in block
    assert "filler 3" not in block

    # And the producer path threads it into the system frame as quoted data.
    messages = build_messages(history, token_budget=800, recalled=block)
    system_text = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "not shown below" in system_text
    assert "retry exactly three times" in system_text
    assert "<quoted-context" in system_text


@pytest.mark.asyncio
async def test_recall_block_empty_when_nothing_elided(sf):
    index, embedder = _index(sf)
    history = [_node(0, "short thread"), _node(1, "question?")]
    assert await index.recall_block(history) == ""
    assert embedder.calls == 0  # no windows dropped -> no embedding work at all


@pytest.mark.asyncio
async def test_chat_producer_uses_the_wired_recaller():
    seen = {}

    async def recaller(history):
        seen["n"] = len(history)
        return "alice (user): the recalled decision"

    class OneShotProvider:
        name = "fake"

        async def stream_messages(self, messages):
            seen["system"] = "\n".join(
                m["content"] for m in messages if m["role"] == "system"
            )
            yield "ok"

    filler = [_node(i, "filler " + "z " * 4000) for i in range(9)]
    history = [*filler, _node(9, "the question")]
    producer = ChatProducer(OneShotProvider(), recaller=recaller)
    events = [e async for e in producer.run(history)]

    assert isinstance(events[0], Token)
    assert seen["n"] == 10  # recaller got the full history
    assert "the recalled decision" in seen["system"]  # and its block was used


@pytest.mark.asyncio
async def test_concurrent_ensure_folds_the_unique_race(sf):
    """The send path's fire-and-forget embed and a search's backfill can hit
    the same node at once; both see it missing, both insert, and the loser
    used to surface the UNIQUE violation as a 500. The loser must fold —
    the winner already wrote the identical vector."""
    import asyncio
    import threading

    barrier = threading.Barrier(2, timeout=5)

    class BarrierEmbedder(CountingEmbedder):
        # Neither ensure() may commit until both have read "missing" and
        # reached the embed step — the race, made deterministic.
        def embed(self, texts):
            barrier.wait()
            return super().embed(texts)

    embedder = BarrierEmbedder()
    index = EmbeddingIndex(sf, memory=FakeMemory(embedder))
    node = _node(1, "we retry three times")

    await asyncio.gather(index.ensure([node]), index.ensure([node]))

    async with sf() as session:
        rows = (await session.execute(select(NodeEmbeddingRow))).scalars().all()
    assert [r.node_id for r in rows] == ["n1"]
