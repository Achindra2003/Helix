"""Document ingestion + retrieval — the AI half of file grounding.

Retrieval design, decided and owned here: **dense vectors on the shared
embedder**, the same substrate as node embeddings (MiniLM locally, lexical
hashed-BoW fallback in minimal installs — both are vector-shaped, so one code
path). The vectorless alternatives were considered and rejected for this
scale: BM25 adds an index dependency to win exact-term lookups that the
lexical fallback already approximates, and an LLM-as-retriever spends tokens
per send on the workspace's own key. Chunks live in the ordinary DB; cosine
over a workspace's chunks in Python is microseconds up to ~10⁵ chunks, which
is far past a team workspace's realistic document pool. Revisit (pgvector)
only past that.

Grounding at send time is *relevance-gated*: chunks below the floor stay out,
so an unrelated question doesn't drag the knowledge base into every prompt.
Grounded text enters the context inside the same `<quoted-context>` boundary
as references — the injection defenses apply to documents automatically.
"""
from __future__ import annotations

import asyncio
import io
from array import array

from sqlalchemy import delete, select

from ..config import settings
from .models import DocumentChunkRow, DocumentRow

# --- extraction ---------------------------------------------------------------

# Extensions treated as plain text (decoded, never rejected).
_TEXTY = (
    ".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".yaml", ".yml",
    ".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h",
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
    if name.endswith(_TEXTY) or "." not in name:
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


class DocumentIndex:
    """Ingest documents and retrieve grounding chunks for a workspace."""

    def __init__(self, session_factory, *, memory=None) -> None:
        self._sf = session_factory
        self._memory = memory  # injectable for tests; default = engine embedder

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
        floor: float | None = None,
    ) -> list[dict]:
        """Top-`k` chunks relevant to `query`, with scores and identity —
        the shape both the grounding path and the search endpoint return."""
        from ..telemetry import tracer

        if not query.strip():
            return []
        k = k or settings.grounding_k
        floor = settings.grounding_floor if floor is None else floor
        with tracer().start_as_current_span("retrieval.documents") as span:
            span.set_attribute("retrieval.k", k)
            span.set_attribute("retrieval.floor", floor)
            chunks = await self._workspace_chunks(workspace_id)
            span.set_attribute("retrieval.candidates", len(chunks))
            if not chunks:
                return []
            vecs = await self._current_vectors(chunks)
            query_vec = (await self._embed([query[:2000]]))[0]
            cosine = self._mem().cosine_similarity
            scored = sorted(
                ((cosine(query_vec, vecs[c.id]), c) for c in chunks),
                key=lambda pair: pair[0],
                reverse=True,
            )
            picked = [(s, c) for s, c in scored[:k] if s > floor]
            span.set_attribute("retrieval.hits", len(picked))
            if picked:
                span.set_attribute("retrieval.top_score", round(float(picked[0][0]), 4))
        if not picked:
            return []
        # Filenames for citations, one read.
        async with self._sf() as session:
            result = await session.execute(
                select(DocumentRow).where(
                    DocumentRow.id.in_({c.document_id for _, c in picked})
                )
            )
            names = {d.id: d.filename for d in result.scalars()}
        return [
            {
                "document_id": c.document_id,
                "filename": names.get(c.document_id, "document"),
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
            label = _sanitize_title(f"{hit['filename']} (part {hit['chunk_index'] + 1})")
            excerpt = hit["content"][: settings.grounding_chunk_chars]
            sections.append(
                f'<quoted-context source="document: {label}">\n'
                f"{excerpt}\n</quoted-context>"
            )
            citations.append(
                {
                    "document_id": hit["document_id"],
                    "filename": hit["filename"],
                    "chunk_index": hit["chunk_index"],
                    "score": hit["score"],
                    "excerpt": excerpt[:200],
                }
            )
        return "\n\n".join(sections), citations
