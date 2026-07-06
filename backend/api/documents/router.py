"""HTTP surface for workspace documents (the knowledge base).

RBAC mirrors the rest of the product: any member reads (list/search — the
grounding they'd see in chat anyway), Collaborator+ uploads, and deletion is
the uploader or an owner. Upload returns immediately with status="processing";
ingestion (extract → chunk → embed) runs in the background — poll the list or
detail until "ready"/"error".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import SessionLocal, get_session
from ..deps import get_current_user, get_membership
from ..errors import api_error
from ..models import ROLE_COLLABORATOR, ROLE_OWNER, ROLE_RANK, User
from .models import DocumentChunkRow, DocumentRow
from .service import DocumentIndex

router = APIRouter(prefix="/api", tags=["documents"])

_index = DocumentIndex(SessionLocal)


class SearchRequest(BaseModel):
    query: str
    k: int = 6


def _doc_out(d: DocumentRow) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "mime": d.mime,
        "size_bytes": d.size_bytes,
        "status": d.status,
        "error": d.error,
        "text_chars": d.text_chars,
        "chunk_count": d.chunk_count,
        "author_id": d.author_id,
        "created_at": d.created_at.isoformat(),
    }


async def _require_member(
    workspace_id: str, user: User, session: AsyncSession, min_role: str | None = None
):
    membership = await get_membership(workspace_id, user, session)
    if min_role is not None and ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
        raise api_error(403, "forbidden", f"Requires {min_role} role or higher.")
    return membership


@router.post("/workspaces/{workspace_id}/documents")
async def upload_document(
    workspace_id: str,
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Accept the file, persist the document row, ingest in the background."""
    await _require_member(workspace_id, user, session, ROLE_COLLABORATOR)
    data = await file.read()
    if len(data) > settings.document_max_bytes:
        raise api_error(
            413,
            "too_large",
            f"File exceeds the {settings.document_max_bytes // (1024 * 1024)} MB limit.",
        )
    if not data:
        raise api_error(400, "bad_request", "empty file")
    doc = DocumentRow(
        workspace_id=workspace_id,
        author_id=user.id,
        filename=(file.filename or "document")[:200],
        mime=file.content_type or "",
        size_bytes=len(data),
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    if settings.documents_ingest_inline:  # deterministic path for tests
        await _index.ingest(doc.id, doc.filename, data)
        await session.refresh(doc)
    else:
        _index.ingest_soon(doc.id, doc.filename, data)
    return _doc_out(doc)


@router.get("/workspaces/{workspace_id}/documents")
async def list_documents(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _require_member(workspace_id, user, session)
    result = await session.execute(
        select(DocumentRow)
        .where(DocumentRow.workspace_id == workspace_id)
        .order_by(DocumentRow.created_at.desc())
    )
    return {"items": [_doc_out(d) for d in result.scalars()]}


@router.get("/workspaces/{workspace_id}/documents/{document_id}")
async def get_document(
    workspace_id: str,
    document_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _require_member(workspace_id, user, session)
    doc = await session.get(DocumentRow, document_id)
    if doc is None or doc.workspace_id != workspace_id:
        raise api_error(404, "not_found", "document not found")
    return _doc_out(doc)


@router.delete("/workspaces/{workspace_id}/documents/{document_id}")
async def delete_document(
    workspace_id: str,
    document_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Uploader or workspace owner. Chunks go with the document — grounding
    stops citing it on the next send."""
    membership = await _require_member(workspace_id, user, session, ROLE_COLLABORATOR)
    doc = await session.get(DocumentRow, document_id)
    if doc is None or doc.workspace_id != workspace_id:
        raise api_error(404, "not_found", "document not found")
    if doc.author_id != user.id and membership.role != ROLE_OWNER:
        raise api_error(403, "forbidden", "Only the uploader or an owner may delete.")
    await session.execute(
        delete(DocumentChunkRow).where(DocumentChunkRow.document_id == document_id)
    )
    await session.delete(doc)
    await session.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/documents/search")
async def search_documents(
    workspace_id: str,
    body: SearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Direct retrieval over the workspace knowledge base — the same ranking
    the chat grounding uses, exposed for a search UI / debugging relevance."""
    await _require_member(workspace_id, user, session)
    hits = await _index.search(workspace_id, body.query, k=max(1, min(body.k, 20)))
    for hit in hits:
        hit["content"] = hit["content"][:600]  # response hygiene; full text lives in chunks
    return {"items": hits}
