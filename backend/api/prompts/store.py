"""The prompt library store — save / get / list+search, workspace-scoped.

Durable on SQLAlchemy (same SQLite-dev / Postgres-prod story as the conversation
store). Search filters in Python: a free-text `query` matches title or body, and
`tag` matches an exact tag — both case-insensitive. Workspaces are small, so
loading a workspace's prompts and filtering in memory is simpler and correct.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import select


@dataclass
class Prompt:
    id: str
    workspace_id: str
    author_id: str
    title: str
    body: str
    tags: list[str] = field(default_factory=list)


def _norm_tags(tags: list[str] | None) -> list[str]:
    """Lowercase, strip, de-dup (order-preserving) — so tag search is predictable."""
    out: list[str] = []
    for t in tags or []:
        t = t.strip().lower()
        if t and t not in out:
            out.append(t)
    return out


class PromptStore:
    """Workspace-scoped prompt library on SQLAlchemy."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_prompt(row) -> Prompt:
        return Prompt(
            id=row.id,
            workspace_id=row.workspace_id,
            author_id=row.author_id,
            title=row.title,
            body=row.body,
            tags=json.loads(row.tags or "[]"),
        )

    async def save(
        self, *, workspace_id: str, author_id: str, title: str, body: str,
        tags: list[str] | None = None,
    ) -> Prompt:
        from .models import PromptRow

        async with self._sf() as s:
            row = PromptRow(
                workspace_id=workspace_id,
                author_id=author_id,
                title=title,
                body=body,
                tags=json.dumps(_norm_tags(tags)),
            )
            s.add(row)
            await s.commit()
            return self._to_prompt(row)

    async def get(self, prompt_id: str) -> Prompt | None:
        from .models import PromptRow

        async with self._sf() as s:
            row = await s.get(PromptRow, prompt_id)
            return self._to_prompt(row) if row else None

    async def update(
        self, prompt_id: str, *, title: str, body: str, tags: list[str] | None = None
    ) -> Prompt | None:
        from .models import PromptRow

        async with self._sf() as s:
            row = await s.get(PromptRow, prompt_id)
            if row is None:
                return None
            row.title = title
            row.body = body
            row.tags = json.dumps(_norm_tags(tags))
            await s.commit()
            return self._to_prompt(row)

    async def delete(self, prompt_id: str) -> bool:
        from .models import PromptRow

        async with self._sf() as s:
            row = await s.get(PromptRow, prompt_id)
            if row is None:
                return False
            await s.delete(row)
            await s.commit()
            return True

    async def list(
        self, workspace_id: str, *, query: str | None = None, tag: str | None = None
    ) -> list[Prompt]:
        from .models import PromptRow

        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(PromptRow)
                    .where(PromptRow.workspace_id == workspace_id)
                    .order_by(PromptRow.created_at.desc())
                )
            ).scalars().all()

        prompts = [self._to_prompt(r) for r in rows]
        if query:
            q = query.lower()
            prompts = [p for p in prompts if q in p.title.lower() or q in p.body.lower()]
        if tag:
            t = tag.strip().lower()
            prompts = [p for p in prompts if t in p.tags]
        return prompts
