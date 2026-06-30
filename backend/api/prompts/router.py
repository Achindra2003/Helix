"""HTTP surface for the shared prompt library (F4).

Workspace-scoped save/list/search plus single-prompt fetch. The *insert* path —
running a saved prompt as a conversation turn — lives in the conversation router,
where the engine and conversation store already are.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import SessionLocal
from .store import PromptStore

router = APIRouter(tags=["prompts"])

_store = PromptStore(SessionLocal)


class CreatePrompt(BaseModel):
    author_id: str = "u1"
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


@router.post("/workspaces/{workspace_id}/prompts")
async def create_prompt(workspace_id: str, body: CreatePrompt):
    prompt = await _store.save(
        workspace_id=workspace_id,
        author_id=body.author_id,
        title=body.title,
        body=body.body,
        tags=body.tags,
    )
    return _to_dict(prompt)


@router.get("/workspaces/{workspace_id}/prompts")
async def list_prompts(workspace_id: str, q: str | None = None, tag: str | None = None):
    prompts = await _store.list(workspace_id, query=q, tag=tag)
    return {"prompts": [_to_dict(p) for p in prompts]}


@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: str):
    prompt = await _store.get(prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "prompt not found"}
        )
    return _to_dict(prompt)
