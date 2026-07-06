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
