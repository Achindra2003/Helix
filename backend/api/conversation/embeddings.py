"""Persisted node embeddings — the workspace's retrieval substrate.

Nodes are immutable, so each one's embedding is computed once and stored,
instead of re-embedded on every send (which also *blocked the event loop*:
sentence-transformers is synchronous — all embedding here runs in a worker
thread). The rows are versioned by embedder name, so upgrading the embedder is
a lazy re-embed on next read, never a migration crisis: a row whose version
doesn't match the active embedder is simply recomputed and overwritten.

This table is deliberately the *one* substrate under everything retrieval-
shaped: semantic recall of elided turns (wired here), workspace memory and
file-chunk grounding (they add rows in the same shape). Vectors are packed
float32 bytes — SQLite and Postgres both store them as-is; no vector-DB
dependency at this scale, by design (cosine over a few hundred candidates in
Python is microseconds; revisit only if candidate sets grow past ~10⁵).
"""
from __future__ import annotations

import asyncio
from array import array

from sqlalchemy import LargeBinary, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import _now
from datetime import datetime

from .events import Node


class NodeEmbeddingRow(Base):
    """One node's embedding under one embedder version (latest only)."""

    __tablename__ = "node_embeddings"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String)  # embedder name, e.g. MiniLM
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(default=_now)


def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    out = array("f")
    out.frombytes(blob)
    return list(out)


def _get_engine_memory():
    """The engine's embedder module (neural when installed, lexical fallback)."""
    from engine.ouroboros_bootstrap import load_ouroboros

    return load_ouroboros().memory


class EmbeddingIndex:
    """Embed-once storage + similarity reads over persisted node vectors."""

    def __init__(self, session_factory, *, memory=None) -> None:
        self._sf = session_factory
        # Injectable for tests; the default is the engine's shared embedder.
        self._memory = memory

    def _mem(self):
        if self._memory is None:
            self._memory = _get_engine_memory()
        return self._memory

    @property
    def version(self) -> str:
        return getattr(self._mem().get_embedder(), "name", "unknown")

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed in a worker thread — the model is sync and CPU-bound."""
        embedder = self._mem().get_embedder()
        return await asyncio.to_thread(embedder.embed, texts)

    async def ensure(self, nodes: list[Node]) -> None:
        """Embed and persist any of `nodes` lacking a current-version row.

        Idempotent and lazy: already-embedded nodes cost one indexed read; a
        version mismatch (embedder upgraded) re-embeds and overwrites. This is
        both the write path (called after a node persists) and the backfill
        (pre-substrate nodes get rows the first time retrieval wants them).
        """
        todo = [n for n in nodes if n.content.strip()]
        if not todo:
            return
        version = self.version
        async with self._sf() as session:
            result = await session.execute(
                select(NodeEmbeddingRow).where(
                    NodeEmbeddingRow.node_id.in_([n.id for n in todo])
                )
            )
            rows = {r.node_id: r for r in result.scalars()}
            missing = [
                n for n in todo
                if n.id not in rows or rows[n.id].version != version
            ]
            if not missing:
                return
            vectors = await self._embed([n.content[:4000] for n in missing])
            for node, vec in zip(missing, vectors):
                row = rows.get(node.id)
                if row is None:
                    session.add(
                        NodeEmbeddingRow(
                            node_id=node.id, version=version, vector=_pack(vec)
                        )
                    )
                else:  # embedder upgraded: overwrite in place
                    row.version = version
                    row.vector = _pack(vec)
            await session.commit()

    def ensure_soon(self, node: Node) -> None:
        """Fire-and-forget embed-on-write (the hot path must not wait on it).

        A lost task is harmless: `ensure` backfills on first retrieval."""
        async def _bg():
            try:
                await self.ensure([node])
            except Exception:
                pass  # retrieval-time ensure() is the safety net

        try:
            asyncio.get_running_loop().create_task(_bg())
        except RuntimeError:  # no loop (sync test context) — backfill covers it
            pass

    async def drop(self, node_ids: list[str]) -> None:
        """Remove persisted vectors for nodes that no longer exist (e.g. the
        "delete my last message" path) — otherwise they'd sit as orphaned
        rows keyed to a node_id nothing points to."""
        if not node_ids:
            return
        from sqlalchemy import delete

        async with self._sf() as session:
            await session.execute(
                delete(NodeEmbeddingRow).where(NodeEmbeddingRow.node_id.in_(node_ids))
            )
            await session.commit()

    async def vectors(self, node_ids: list[str]) -> dict[str, list[float]]:
        """Current-version vectors for `node_ids` (missing/stale ids omitted)."""
        if not node_ids:
            return {}
        version = self.version
        async with self._sf() as session:
            result = await session.execute(
                select(NodeEmbeddingRow).where(
                    NodeEmbeddingRow.node_id.in_(node_ids),
                    NodeEmbeddingRow.version == version,
                )
            )
            return {r.node_id: _unpack(r.vector) for r in result.scalars()}

    async def rank(self, query: str, nodes: list[Node], *, k: int = 4,
                   floor: float = 0.1) -> list[Node]:
        """The top-`k` of `nodes` most similar to `query`, chronological order.

        Node vectors come from the persisted substrate (backfilled on demand);
        only the query is embedded per call.
        """
        from ..telemetry import tracer

        if not nodes or not query.strip():
            return []
        with tracer().start_as_current_span("retrieval.recall") as span:
            span.set_attribute("retrieval.k", k)
            span.set_attribute("retrieval.candidates", len(nodes))
            await self.ensure(nodes)
            vecs = await self.vectors([n.id for n in nodes])
            query_vec = (await self._embed([query[:2000]]))[0]
            cosine = self._mem().cosine_similarity
            scored = sorted(
                (
                    (cosine(query_vec, vecs[n.id]), i)
                    for i, n in enumerate(nodes)
                    if n.id in vecs
                ),
                reverse=True,
            )
            picks = sorted(i for score, i in scored[:k] if score > floor)
            span.set_attribute("retrieval.hits", len(picks))
            return [nodes[i] for i in picks]

    async def search_workspace(
        self, workspace_id: str, viewer_id: str, query: str, *,
        k: int = 10, floor: float = 0.15,
    ) -> list[dict]:
        """Semantic search across every node the caller can see in a
        workspace — shared conversations, plus their own private ones.

        Mirrors `DocumentIndex.search`'s shape but over conversation nodes
        instead of document chunks. `node_embeddings` carries no
        `workspace_id` of its own, so this joins through
        `NodeRow -> BranchRow -> ConversationRow` and reuses the exact
        visibility clause `DbStore.list_conversations` applies, so a search
        can never surface a private thread that isn't the caller's own.
        """
        if not query.strip():
            return []
        from sqlalchemy import or_, select

        from .models import BranchRow, ConversationRow, NodeRow

        async with self._sf() as session:
            rows = (
                await session.execute(
                    select(NodeRow, BranchRow.conversation_id, ConversationRow.title)
                    .join(BranchRow, BranchRow.id == NodeRow.branch_id)
                    .join(ConversationRow, ConversationRow.id == BranchRow.conversation_id)
                    .where(
                        ConversationRow.workspace_id == workspace_id,
                        NodeRow.content != "",
                        or_(
                            ConversationRow.visibility != "private",
                            ConversationRow.author_id == viewer_id,
                        ),
                    )
                )
            ).all()
        if not rows:
            return []

        nodes = [
            Node(
                id=r.id, branch_id=r.branch_id, parent_id=r.parent_id, seq=r.seq,
                role=r.role, content=r.content, author_id=r.author_id,
                token_count=r.token_count,
            )
            for r, _cid, _title in rows
        ]
        meta = {r.id: (cid, title, r.created_at) for r, cid, title in rows}

        await self.ensure(nodes)
        vecs = await self.vectors([n.id for n in nodes])
        query_vec = (await self._embed([query[:2000]]))[0]
        cosine = self._mem().cosine_similarity
        scored = sorted(
            ((cosine(query_vec, vecs[n.id]), n) for n in nodes if n.id in vecs),
            key=lambda pair: pair[0],
            reverse=True,
        )
        picked = [(score, n) for score, n in scored[:k] if score > floor]
        return [
            {
                "node_id": n.id,
                "conversation_id": meta[n.id][0],
                "conversation_title": meta[n.id][1],
                "branch_id": n.branch_id,
                "role": n.role,
                "excerpt": n.content[:240],
                "score": round(float(score), 4),
                "author_id": n.author_id,
                "created_at": meta[n.id][2].isoformat(),
            }
            for score, n in picked
        ]

    async def recall_block(self, history: list[Node]) -> str:
        """The rendered recall block for a send: elided turns most relevant to
        the current question, from persisted vectors. This is the `recaller`
        the producers call; any failure degrades to recency (never silence,
        never a failed send — recall is an enhancement, not a dependency)."""
        from .context import plan_recall, render_recall_lines

        elided, query = plan_recall(history)
        if not elided or not query.strip():
            return ""
        try:
            picks = await self.rank(query, elided)
        except Exception:
            picks = elided[-4:]
        return render_recall_lines(picks)
