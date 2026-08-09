"""Document ingestion + retrieval — the AI half of file grounding.

Retrieval design, decided and owned here: **dense vectors on the shared
embedder**, the same substrate as node embeddings (MiniLM locally, lexical
hashed-BoW fallback in minimal installs — both are vector-shaped, so one code
path). The vectorless alternatives were considered and rejected for this
scale: BM25 adds an index dependency to win exact-term lookups that the
lexical fallback already approximates, and an LLM-as-retriever spends tokens
per send on the workspace's own key.

Chunks live in the ordinary DB — no vector server. This file used to claim
that scoring them "is microseconds up to ~10⁵ chunks"; it was not, and the
number was never measured. Scoring every chunk with a Python generator
expression and rebuilding BM25 per query cost **1.28 s at 10,000 chunks**,
per grounded send.

What made that claim true instead of merely optimistic: the workspace's
vectors are held as one float32 matrix and scored with a single matrix
product, BM25 keeps postings so it only visits documents that contain a query
term, and both are built once and reused until the corpus changes
(`_WorkspaceIndex`, invalidated by `CorpusRevisionRow`). The same query is
**7 ms at 10,000** and 34 ms at 50,000 — past a serious literature review,
in-process, with no extra infrastructure.

The next step up is an approximate index (pgvector/FAISS), and it is a real
step: it trades exactness for sublinear search. Nothing here needs it yet.

Grounding at send time is *relevance-gated*: chunks below the floor stay out,
so an unrelated question doesn't drag the knowledge base into every prompt.
Grounded text enters the context inside the same `<quoted-context>` boundary
as references — the injection defenses apply to documents automatically.
"""
from __future__ import annotations

import asyncio
import io
from array import array
from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, select

from ..config import settings
from .models import (
    CorpusRevisionRow,
    DocumentChunkRow,
    DocumentRow,
    bump_corpus_revision,
    cite_as,
)

# --- extraction ---------------------------------------------------------------

# Extensions treated as plain text (decoded, never rejected).
_TEXTY = (
    ".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".yaml", ".yml",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".sql", ".html", ".css", ".xml", ".toml", ".ini", ".log",
)


def extract_text(filename: str, data: bytes) -> str:
    """Extracted text, or raise ValueError with a user-showable reason."""
    name = filename.lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - env guard
            raise ValueError("PDF support requires the pypdf package") from exc
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            raise ValueError(f"could not read PDF: {type(exc).__name__}") from exc
        if not text.strip():
            raise ValueError("PDF contains no extractable text (scanned images?)")
        return text
    if name.endswith(_TEXTY):
        return data.decode("utf-8", errors="replace")
    if "." not in name:
        # Extensionless files are usually real text (README, Makefile,
        # Dockerfile), so they stay welcome — but the name proves nothing, and
        # decoding a binary with errors="replace" would ingest a wall of
        # replacement characters that grounding could then cite. A NUL byte in
        # the head is the cheap, reliable tell that this is not text.
        if b"\x00" in data[:8192]:
            raise ValueError(
                "unsupported file type — this looks like binary data; "
                "give it a .txt/.md/code extension if it really is text"
            )
        return data.decode("utf-8", errors="replace")
    raise ValueError(
        "unsupported file type — upload text/markdown/code files or PDFs"
    )


# --- chunking -------------------------------------------------------------------

_CHUNK_WORDS = 220
_OVERLAP_WORDS = 40


def chunk_text(text: str, *, chunk_words: int = _CHUNK_WORDS,
               overlap: int = _OVERLAP_WORDS) -> list[str]:
    """Word-window chunks with overlap, so a fact straddling a boundary is
    whole in at least one chunk. Mirrors the engine's embedding-side chunking."""
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_words:
        return [" ".join(words)]
    step = max(1, chunk_words - overlap)
    return [
        " ".join(words[i : i + chunk_words])
        for i in range(0, len(words), step)
        if words[i : i + chunk_words]
    ]


# --- vector packing (same format as node_embeddings) ----------------------------


def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    out = array("f")
    out.frombytes(blob)
    return list(out)


# --- the index -------------------------------------------------------------------


@dataclass
class _WorkspaceIndex:
    """One workspace's chunks, prepared for scoring rather than for storage.

    Both retrieval arms used to be rebuilt from scratch on every query: the
    dense arm decoded every stored vector into a Python list and scored it with
    a generator expression, and BM25 re-tokenised the entire corpus. That is
    ~1.3 s for one grounded send at 10,000 chunks, measured — which is the size
    a literature review reaches, and it is paid *per message*.

    Here the per-query work is a single matrix product. The rest is built once
    and reused until the corpus changes.
    """

    #: The corpus revision this was built from. See `CorpusRevisionRow`.
    fingerprint: int
    #: Rebuilt from scratch when the embedder changes under us, because every
    #: vector is then in the wrong space and comparing them is meaningless.
    embedder_version: str
    chunks: list
    #: (n, dim) float32. Rows are in `chunks` order.
    matrix: object
    bm25: object


class DocumentIndex:
    """Ingest documents and retrieve grounding chunks for a workspace."""

    def __init__(self, session_factory, *, memory=None) -> None:
        self._sf = session_factory
        self._memory = memory  # injectable for tests; default = engine embedder
        # Per workspace, and per instance rather than module-global: the two
        # long-lived instances (grounding at send time, and the search
        # endpoint) each hold their own, which costs a second copy of the
        # matrix — 15 MB per 10,000 chunks — and keeps tests that build their
        # own index from inheriting another test's corpus.
        self._cache: dict[str, _WorkspaceIndex] = {}

    def _mem(self):
        if self._memory is None:
            from engine.ouroboros_bootstrap import load_ouroboros

            self._memory = load_ouroboros().memory
        return self._memory

    @property
    def version(self) -> str:
        return getattr(self._mem().get_embedder(), "name", "unknown")

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        embedder = self._mem().get_embedder()
        return await asyncio.to_thread(embedder.embed, texts)

    # --- ingestion ---

    async def ingest(self, document_id: str, filename: str, data: bytes) -> None:
        """Extract → chunk → embed → store; stamp the document ready or errored.

        Runs in the background after upload. Every failure lands as
        status="error" with a reason — never a document stuck "processing"."""
        try:
            text = extract_text(filename, data)[: settings.document_max_chars]
            chunks = chunk_text(text)
            if not chunks:
                raise ValueError("document contains no text")
            vectors = await self._embed(chunks)
            version = self.version
            async with self._sf() as session:
                doc = await session.get(DocumentRow, document_id)
                if doc is None:  # deleted while processing
                    return
                # Idempotent re-ingest: replace any previous chunks.
                await session.execute(
                    delete(DocumentChunkRow).where(
                        DocumentChunkRow.document_id == document_id
                    )
                )
                for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                    session.add(
                        DocumentChunkRow(
                            document_id=document_id,
                            workspace_id=doc.workspace_id,
                            idx=i,
                            content=chunk,
                            embedder_version=version,
                            vector=_pack(vec),
                        )
                    )
                doc.status = "ready"
                doc.error = ""
                doc.text_chars = len(text)
                doc.chunk_count = len(chunks)
                # Same transaction as the chunks: every reader's cached index
                # is now stale, and this is what tells them.
                await bump_corpus_revision(session, doc.workspace_id)
                await session.commit()
        except Exception as exc:
            async with self._sf() as session:
                doc = await session.get(DocumentRow, document_id)
                if doc is not None:
                    doc.status = "error"
                    doc.error = str(exc)[:300]
                    await session.commit()

    def ingest_soon(self, document_id: str, filename: str, data: bytes) -> None:
        """Fire-and-forget ingestion (the upload response must not wait on
        embedding). `documents_ingest_inline=True` (tests) awaits instead."""
        asyncio.get_running_loop().create_task(
            self.ingest(document_id, filename, data)
        )

    # --- retrieval ---

    async def _workspace_chunks(self, workspace_id: str) -> list[DocumentChunkRow]:
        async with self._sf() as session:
            result = await session.execute(
                select(DocumentChunkRow).where(
                    DocumentChunkRow.workspace_id == workspace_id
                )
            )
            return list(result.scalars())

    async def _revision(self, workspace_id: str) -> int:
        """This workspace's corpus revision — one primary-key lookup.

        See `CorpusRevisionRow` for why this is a counter rather than the
        obvious COUNT/MAX probe over the chunks themselves.
        """
        async with self._sf() as session:
            row = await session.get(CorpusRevisionRow, workspace_id)
            return row.revision if row else 0

    async def _index_for(self, workspace_id: str) -> _WorkspaceIndex | None:
        """The workspace's scoring index, built once and reused.

        Returns None for an empty workspace, which is the common case on a new
        instance and must not cost a matrix allocation.
        """
        revision = await self._revision(workspace_id)
        if revision == 0:
            self._cache.pop(workspace_id, None)
            return None

        version = self.version
        cached = self._cache.get(workspace_id)
        if (
            cached is not None
            and cached.fingerprint == revision
            and cached.embedder_version == version
        ):
            return cached

        from .lexical import BM25

        chunks = await self._workspace_chunks(workspace_id)
        if not chunks:
            self._cache.pop(workspace_id, None)
            return None
        vectors = await self._current_vectors(chunks)
        # float32, not float64: these came from a float32 store, the extra
        # precision is invented, and it doubles both the memory and the time.
        matrix = np.asarray([vectors[c.id] for c in chunks], dtype=np.float32)
        index = _WorkspaceIndex(
            fingerprint=revision,
            embedder_version=version,
            chunks=chunks,
            matrix=matrix,
            bm25=BM25([c.content for c in chunks]),
        )
        self._cache[workspace_id] = index
        return index

    async def _current_vectors(
        self, chunks: list[DocumentChunkRow]
    ) -> dict[str, list[float]]:
        """Vectors for `chunks`, lazily re-embedding any stale-version rows
        (the embedder-upgrade path — content is stored, so it's transparent)."""
        version = self.version
        out = {
            c.id: _unpack(c.vector) for c in chunks if c.embedder_version == version
        }
        stale = [c for c in chunks if c.embedder_version != version]
        if stale:
            vectors = await self._embed([c.content for c in stale])
            async with self._sf() as session:
                for chunk, vec in zip(stale, vectors):
                    row = await session.get(DocumentChunkRow, chunk.id)
                    if row is not None:
                        row.embedder_version = version
                        row.vector = _pack(vec)
                await session.commit()
            out.update({c.id: v for c, v in zip(stale, vectors)})
        return out

    async def search(
        self, workspace_id: str, query: str, *, k: int | None = None,
        floor: float | None = None, mode: str | None = None,
    ) -> list[dict]:
        """Top-`k` chunks relevant to `query`, with scores and identity —
        the shape both the grounding path and the search endpoint return.

        Hybrid retrieval (the default `mode`): dense cosine and BM25 each
        rank the workspace's chunks, rankings fuse by RRF, and a chunk is
        *eligible* if either signal clears its floor — dense catches
        paraphrase, lexical catches exact rare terms (error codes, config
        names) whose embeddings carry almost no signal. `mode` exists so the
        retrieval eval harness can measure each arm alone; thresholds here
        are chosen from that harness's report, not vibes.
        """
        from ..telemetry import tracer
        from .lexical import rrf_fuse, squash

        if not query.strip():
            return []
        k = k or settings.grounding_k
        floor = settings.grounding_floor if floor is None else floor
        mode = mode or settings.grounding_retrieval_mode
        with tracer().start_as_current_span("retrieval.documents") as span:
            span.set_attribute("retrieval.k", k)
            span.set_attribute("retrieval.floor", floor)
            span.set_attribute("retrieval.mode", mode)
            index = await self._index_for(workspace_id)
            if index is None:
                span.set_attribute("retrieval.candidates", 0)
                return []
            chunks = index.chunks
            span.set_attribute("retrieval.candidates", len(chunks))

            n = len(chunks)
            dense = [0.0] * n
            if mode != "lexical":
                query_vec = (await self._embed([query[:2000]]))[0]
                # A dot product, not a normalised cosine: the embedders emit
                # unit vectors and `memory.cosine_similarity` is itself a plain
                # dot. Normalising here would silently move every score and
                # invalidate the measured relevance floors.
                dense = (
                    index.matrix @ np.asarray(query_vec, dtype=np.float32)
                ).tolist()
            lex = [0.0] * n
            if mode != "dense":
                lex = [squash(s) for s in index.bm25.scores(query)]

            # Relevance gate: either signal clearing its floor admits a chunk.
            # The dense floor's calibration story lives in config.py; the
            # lexical floor is in squashed-BM25 units, measured on the golden
            # set (evals/retrieval.py) so negatives stay leak-free.
            lex_floor = settings.grounding_lexical_floor
            eligible = [
                i for i in range(n) if dense[i] > floor or lex[i] > lex_floor
            ]
            if not eligible:
                span.set_attribute("retrieval.hits", 0)
                return []

            rankings = []
            if mode != "lexical":
                rankings.append(sorted(eligible, key=lambda i: dense[i], reverse=True))
            if mode != "dense":
                lex_hits = [i for i in eligible if lex[i] > 0]
                if lex_hits:
                    rankings.append(sorted(lex_hits, key=lambda i: lex[i], reverse=True))
            fused = rrf_fuse(rankings)
            top = sorted(eligible, key=lambda i: fused.get(i, 0.0), reverse=True)[:k]
            # Reported relevance = the stronger of the two signals (both live
            # in 0..1); the fused RRF value itself is rank math, not meaning.
            picked = [(max(dense[i], lex[i]), chunks[i]) for i in top]
            span.set_attribute("retrieval.hits", len(picked))
            if picked:
                span.set_attribute("retrieval.top_score", round(float(picked[0][0]), 4))
        if not picked:
            return []
        # Identities for citations, one read.
        async with self._sf() as session:
            result = await session.execute(
                select(DocumentRow).where(
                    DocumentRow.id.in_({c.document_id for _, c in picked})
                )
            )
            docs = {d.id: d for d in result.scalars()}
        return [
            {
                "document_id": c.document_id,
                "filename": (
                    docs[c.document_id].filename
                    if c.document_id in docs
                    else "document"
                ),
                # How this source should be *named*: "Smith et al. (2019)" once
                # someone has catalogued it, the filename until then. Carried
                # alongside the filename rather than replacing it, because the
                # file is still what a reader opens.
                "cite_as": (
                    cite_as(docs[c.document_id])
                    if c.document_id in docs
                    else "document"
                ),
                "chunk_index": c.idx,
                "score": round(float(s), 4),
                "content": c.content,
            }
            for s, c in picked
        ]

    async def grounding_block(
        self, workspace_id: str, history: list
    ) -> tuple[str, list[dict]]:
        """The grounding for one send: a quoted-data block for the system frame
        plus the citation items for the stream. Empty when nothing clears the
        relevance floor — grounding is invited by relevance, never forced. Any
        failure returns empty: grounding is an enhancement, not a dependency."""
        from ..conversation.context import _DATA_NOT_INSTRUCTIONS, _sanitize_title

        query = next(
            (n.content for n in reversed(history) if n.role == "user"), ""
        )
        try:
            hits = await self.search(workspace_id, query)
        except Exception:
            return "", []
        if not hits:
            return "", []
        sections = [_DATA_NOT_INSTRUCTIONS]
        citations = []
        for hit in hits:
            # The model is shown the citable name, not the filename: when it
            # says "according to the spec" in its reply, it should be able to
            # say "according to Smith et al. (2019)" instead — which is the
            # whole reason a research team catalogues anything.
            label = _sanitize_title(
                f"{hit.get('cite_as') or hit['filename']} (part {hit['chunk_index'] + 1})"
            )
            excerpt = hit["content"][: settings.grounding_chunk_chars]
            sections.append(
                f'<quoted-context source="document: {label}">\n'
                f"{excerpt}\n</quoted-context>"
            )
            citations.append(
                {
                    "document_id": hit["document_id"],
                    "filename": hit["filename"],
                    "cite_as": hit.get("cite_as") or hit["filename"],
                    "chunk_index": hit["chunk_index"],
                    "score": hit["score"],
                    "excerpt": excerpt[:200],
                }
            )
        return "\n\n".join(sections), citations
