"""The workspace Map: one aggregate read of the team's reasoning structure.

``GET /workspaces/{workspace_id}/map`` returns every conversation the caller
may see (shared ones, plus their *own* private threads — same visibility rule
as the list route), each with its branch tree, its node *skeleton*, and its
outgoing reference edges. One round-trip powers the whole Map view instead of
N ``branches`` + N ``history`` calls.

Nodes are stripped to structure (id / branch / parent / seq / role / author) —
no content — so a busy workspace still ships a small payload; the Map fetches
message excerpts lazily from the existing history route on hover.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import User
from . import router as conversation_router_mod

router = APIRouter(tags=["map"])


@router.get("/workspaces/{workspace_id}/map")
async def workspace_map(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The reasoning graph of a workspace, scoped to the authenticated caller."""
    # Same store + guards the conversation routes use (module attribute so the
    # tests' in-memory store swap applies here too).
    store = conversation_router_mod._store
    await conversation_router_mod._require_membership(workspace_id, user, session)

    out = []
    for conv in await store.list_conversations(workspace_id, user.id):
        branches = await store.list_branches(conv.id)
        # Each branch's history walks back across fork boundaries, so ancestor
        # nodes appear in several histories — dedupe by id. A node's own
        # `branch_id` stays intact, which is what the layout groups by.
        seen: dict[str, dict] = {}
        for branch in branches:
            for node in await store.get_history(branch.id):
                if node.id not in seen:
                    seen[node.id] = {
                        "id": node.id,
                        "branch_id": node.branch_id,
                        "parent_id": node.parent_id,
                        "seq": node.seq,
                        "role": node.role,
                        "author_id": node.author_id,
                    }
        out.append(
            {
                "id": conv.id,
                "title": conv.title,
                "visibility": conv.visibility,
                "author_id": conv.author_id,
                "default_branch_id": conv.default_branch_id,
                "branches": [
                    {
                        "id": b.id,
                        "name": b.name,
                        "parent_branch_id": b.parent_branch_id,
                        "fork_node_id": b.fork_node_id,
                        "head_node_id": b.head_node_id,
                    }
                    for b in branches
                ],
                "nodes": list(seen.values()),
                "references": await store.list_reference_ids(conv.id),
            }
        )
    return {"conversations": out}
