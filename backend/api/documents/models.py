"""Workspace documents — the knowledge base under file grounding.

A document belongs to the *workspace* (the Claude-Projects-shaped model: one
shared knowledge pool per team space, not per-thread attachments). Ingestion
extracts text, chunks it, and embeds each chunk; retrieval at send time folds
the most relevant chunks into the model's context as quoted data with
citations. The raw file bytes are *not* stored — extracted text is the
product; re-upload is the re-ingest path. (A blob store is the DB teammate's
seam if original-file download ever matters.)
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import _now


def _uuid() -> str:
    return uuid4().hex


class DocumentRow(Base):
    """One uploaded document's identity and ingestion state."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    author_id: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    mime: Mapped[str] = mapped_column(String, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # processing -> ready | error. The upload response returns immediately;
    # extraction/embedding happens in the background (poll the list/detail).
    status: Mapped[str] = mapped_column(String, default="processing")
    error: Mapped[str] = mapped_column(String, default="")
    text_chars: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    # ── bibliographic identity ───────────────────────────────────────────────
    # A research team uploads papers; the index knew only filenames. So a
    # citation read "[smith-et-al-final-v3.pdf — part 4]", which is not a
    # citation — it names a file on somebody's laptop, not a work anyone else
    # can find. These four fields are what turn a chunk reference into a
    # reference.
    #
    # All optional, all editable after upload, and none of them extracted
    # automatically: guessing an author from a PDF's metadata is wrong often
    # enough that a wrong attribution would be worse than a blank one, and this
    # is the field a reader will trust most.
    doc_title: Mapped[str] = mapped_column(String, default="")
    authors: Mapped[str] = mapped_column(String, default="")
    year: Mapped[str] = mapped_column(String, default="")
    # DOI, arXiv id, or a URL — one "where does this live" field rather than
    # three that are usually empty.
    identifier: Mapped[str] = mapped_column(String, default="")


def cite_as(d: DocumentRow) -> str:
    """One short human reference for this document.

    "Smith et al. (2019)" when we know that much, the title when only a title
    was given, the filename otherwise. Never empty: a source with no visible
    name reads as a rendering fault, and the filename is at least true.

    Lives beside the row rather than in the router because three readers need
    the identical string — the citation chip, the exports, and the grounding
    block the *model* sees. If they computed it separately they would drift,
    and a reply that names its source differently from the export beneath it is
    worse than one that names it plainly.
    """
    who = (d.authors or "").strip()
    year = (d.year or "").strip()
    title = (d.doc_title or "").strip()
    if who and year:
        return f"{who} ({year})"
    if who:
        return who
    if title and year:
        return f"{title} ({year})"
    return title or d.filename


class DocumentChunkRow(Base):
    """One retrievable chunk: its text and its embedding, versioned like
    node_embeddings — an embedder upgrade lazily re-embeds from `content`."""

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(String, index=True)  # retrieval scope
    idx: Mapped[int] = mapped_column(Integer)  # position within the document
    content: Mapped[str] = mapped_column(Text)
    embedder_version: Mapped[str] = mapped_column(String, default="")
    vector: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    created_at: Mapped[datetime] = mapped_column(default=_now)
