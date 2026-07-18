"""HTTP surface for the shared prompt library (F4).

Workspace-scoped save/list/search plus single-prompt fetch. The *insert* path —
running a saved prompt as a conversation turn — lives in the conversation router,
where the engine and conversation store already are.

Auth-gated server-side: identity comes from the JWT, reads need workspace
membership (Observer included), saving needs Collaborator or higher.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal, get_session
from ..deps import get_current_user, get_membership
from ..errors import api_error
from ..models import ROLE_COLLABORATOR, ROLE_OWNER, ROLE_RANK, User
from .. import realtime
from .store import PromptStore

router = APIRouter(tags=["prompts"])

_store = PromptStore(SessionLocal)


class CreatePrompt(BaseModel):
    title: str
    body: str
    tags: list[str] = []


def _to_dict(p) -> dict:
    return {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "author_id": p.author_id,
        "title": p.title,
        "body": p.body,
        "tags": p.tags,
    }


async def _require_membership(
    workspace_id: str, user: User, session: AsyncSession, min_role: str | None = None
):
    membership = await get_membership(workspace_id, user, session)
    if min_role is not None and ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
        raise api_error(403, "forbidden", f"Requires {min_role} role or higher.")
    return membership


@router.post("/workspaces/{workspace_id}/prompts")
async def create_prompt(
    workspace_id: str,
    body: CreatePrompt,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _require_membership(workspace_id, user, session, ROLE_COLLABORATOR)
    prompt = await _store.save(
        workspace_id=workspace_id,
        author_id=user.id,
        title=body.title,
        body=body.body,
        tags=body.tags,
    )
    await realtime.broadcast(
        workspace_id,
        {"kind": "prompt.saved", "workspace_id": workspace_id, "prompt": _to_dict(prompt)},
        exclude_user=user.id,
    )
    return _to_dict(prompt)


@router.get("/workspaces/{workspace_id}/prompts")
async def list_prompts(
    workspace_id: str,
    q: str | None = None,
    tag: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _require_membership(workspace_id, user, session)
    prompts = await _store.list(workspace_id, query=q, tag=tag)
    return {"prompts": [_to_dict(p) for p in prompts]}


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    prompt = await _store.get(prompt_id)
    if prompt is None:
        raise api_error(404, "not_found", "prompt not found")
    # Tenancy: the prompt's workspace, derived server-side (404, not 403, so
    # prompt ids can't be probed across tenants).
    try:
        await _require_membership(prompt.workspace_id, user, session)
    except Exception:
        raise api_error(404, "not_found", "prompt not found")
    return _to_dict(prompt)


async def _require_prompt_author_or_owner(prompt_id: str, user: User, session):
    """The prompt, once the caller may edit/delete it: its author, or a
    workspace owner. Same 404 masking as `get_prompt` — outsiders can't
    probe ids, and non-authors get an honest 403."""
    prompt = await _store.get(prompt_id)
    if prompt is None:
        raise api_error(404, "not_found", "prompt not found")
    try:
        membership = await _require_membership(prompt.workspace_id, user, session)
    except Exception:
        raise api_error(404, "not_found", "prompt not found")
    if prompt.author_id != user.id and membership.role != ROLE_OWNER:
        raise api_error(403, "forbidden", "Only the author or an owner can change this prompt.")
    return prompt


class UpdatePrompt(BaseModel):
    title: str
    body: str
    tags: list[str] = []


@router.patch("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: str,
    body: UpdatePrompt,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    prompt = await _require_prompt_author_or_owner(prompt_id, user, session)
    updated = await _store.update(
        prompt_id, title=body.title, body=body.body, tags=body.tags
    )
    await realtime.broadcast(
        prompt.workspace_id,
        {"kind": "prompt.saved", "workspace_id": prompt.workspace_id, "prompt": _to_dict(updated)},
        exclude_user=user.id,
    )
    return _to_dict(updated)


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    prompt = await _require_prompt_author_or_owner(prompt_id, user, session)
    await _store.delete(prompt_id)
    await realtime.broadcast(
        prompt.workspace_id,
        {"kind": "prompt.deleted", "workspace_id": prompt.workspace_id, "prompt_id": prompt_id},
        exclude_user=user.id,
    )
    return {"ok": True}
