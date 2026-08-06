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
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import User, Workspace
from . import reports
from . import router as conversation_router_mod

router = APIRouter(tags=["map"])


@router.get("/workspaces/{workspace_id}/decisions")
async def workspace_decisions(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Every verdict this caller may see, newest first.

    The Map answers "what shape did our thinking take". This answers the
    question a person actually arrives with after a week away: *what did the
    team decide, and why*. Without it the record exists but has no reader —
    you would have to open every conversation and inspect every branch.

    Scoped exactly like the conversation list: shared threads, plus the
    caller's own private ones. Resolved branches only; an open exploration is
    not a decision.
    """
    store = conversation_router_mod._store
    await conversation_router_mod._require_membership(workspace_id, user, session)

    emails: dict[str, str] = {}

    async def _who(user_id: str | None) -> str:
        if not user_id:
            return ""
        if user_id not in emails:
            row = await session.get(User, user_id)
            emails[user_id] = row.email if row else user_id
        return emails[user_id]

    out = []
    for conv in await store.list_conversations(workspace_id, user.id):
        # A thread's conclusion is a decision too — the highest kind, since it
        # is what the team believes after weighing everything below it. Leaving
        # it out would make a ledger called "decisions" miss the real ones.
        if conv.conclusion:
            out.append(
                {
                    "kind": "conclusion",
                    "branch_id": None,
                    "branch_name": "",
                    "conversation_id": conv.id,
                    "conversation_title": conv.title,
                    "visibility": conv.visibility,
                    "intent": "",
                    "status": "concluded",
                    "resolution": conv.conclusion,
                    "resolved_by": conv.concluded_by,
                    "resolved_by_email": await _who(conv.concluded_by),
                    "resolved_at": conv.concluded_at.isoformat() if conv.concluded_at else None,
                }
            )
        for b in await store.list_branches(conv.id):
            if b.status == "open":
                continue
            out.append(
                {
                    "kind": "verdict",
                    "branch_id": b.id,
                    "branch_name": b.name,
                    "conversation_id": conv.id,
                    "conversation_title": conv.title,
                    "visibility": conv.visibility,
                    "intent": b.intent,
                    "status": b.status,
                    "resolution": b.resolution,
                    "resolved_by": b.resolved_by,
                    "resolved_by_email": await _who(b.resolved_by),
                    "resolved_at": b.resolved_at.isoformat() if b.resolved_at else None,
                }
            )
    # Newest decision first; anything without a timestamp sorts last rather
    # than crashing the sort (older rows predate the column).
    out.sort(key=lambda d: d["resolved_at"] or "", reverse=True)
    return {"items": out}


@router.get("/workspaces/{workspace_id}/export")
async def export_workspace_decisions(
    workspace_id: str,
    format: str = "md",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The whole team's decisions, as a document.

    The route above answers "what did we decide?" on screen. This answers it in
    a file — which is the form the question usually takes when it is being
    asked by someone outside the team, or by a reviewer, or a year later.
    Until this existed the only export was a single branch's transcript, so
    "give me everything we've settled" had no answer at all.

    Same visibility rule as the ledger and the conversation list: shared
    threads, plus the caller's own private ones.
    """
    store = conversation_router_mod._store
    await conversation_router_mod._require_membership(workspace_id, user, session)

    workspace = await session.get(Workspace, workspace_id)
    conversations = await store.list_conversations(workspace_id, user.id)
    branches_by_conv = {c.id: await store.list_branches(c.id) for c in conversations}

    report = await reports.build_workspace_report(
        workspace_name=workspace.name if workspace else "Workspace",
        conversations=conversations,
        branches_by_conv=branches_by_conv,
        names=reports.Names(session),
    )
    stem = reports.filename_stem(report["workspace"], "workspace")
    if format == "json":
        return JSONResponse(
            content=report,
            headers={"Content-Disposition": f'attachment; filename="{stem}-decisions.json"'},
        )
    return Response(
        content=reports.render_workspace_markdown(report),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{stem}-decisions.md"'},
    )


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
                        # The verdict travels with the structure: a Map that
                        # shows which explorations were adopted and which were
                        # abandoned is a decision record; one that shows only
                        # the shape is a diagram.
                        "intent": b.intent,
                        "status": b.status,
                        "resolution": b.resolution,
                    }
                    for b in branches
                ],
                "nodes": list(seen.values()),
                "references": await store.list_reference_ids(conv.id),
            }
        )
    return {"conversations": out}
