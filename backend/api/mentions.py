"""Addressing a person.

Helix could already say things *to a room* — a note is a message excluded from
the model's context, so two people in a thread can actually talk. What it could
not do was address anyone. There was no way to write "Priya, is this the number
you meant?" and have Priya find out. Presence told you who was *there*; nothing
let you ask someone to *come*.

A mention is the smallest thing that closes that. `@priya` in a note resolves
against the workspace's own members and leaves a `Notice` for each one — which
outlives the tab, unlike everything the bell held before it.

Deliberate limits, so this stays one idea:

* **Handles are the local part of the email**, matched case-insensitively.
  There is no separate username to choose, register, or collide — the workspace
  already knows exactly who is in it, and a handle nobody had to invent cannot
  drift from the person.
* **Only members of that workspace resolve.** An unresolved `@word` is left as
  ordinary text and notifies nobody. Silence is the correct failure: a mention
  that quietly reached the wrong person would be worse than one that reached
  no one, and the author can see their own note to check.
* **You cannot mention yourself into a notice.** Writing your own name is a
  way of signing something, not a request for your own attention.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Membership, Notice, User

# `@` then a local-part-ish run. Kept narrower than RFC 5321 on purpose: the
# characters people actually put in an address, minus the ones that would eat
# the punctuation of the sentence the mention sits in ("...ask @priya, then").
MENTION = re.compile(r"@([A-Za-z0-9._%+-]+)")

# A mention rendered in the bell needs enough of the sentence to be worth
# opening, and not so much that the bell becomes the reader.
EXCERPT_CHARS = 140


def handles_in(text: str) -> set[str]:
    """Every distinct handle written in `text`, lowercased."""
    return {m.group(1).lower() for m in MENTION.finditer(text)}


def handle_of(email: str) -> str:
    return email.split("@", 1)[0].lower()


async def resolve(
    session: AsyncSession, workspace_id: str, text: str, *, exclude_user_id: str
) -> list[User]:
    """The workspace members `text` addresses, minus the author.

    One query for the workspace's members regardless of how many handles were
    written: a note naming four people should not cost four round trips, and
    the membership of one workspace is small enough to match in Python.
    """
    wanted = handles_in(text)
    if not wanted:
        return []

    rows = (
        await session.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.workspace_id == workspace_id)
        )
    ).scalars().all()

    return [
        u for u in rows
        if u.id != exclude_user_id and handle_of(u.email) in wanted
    ]


async def notify(
    session: AsyncSession,
    *,
    recipients: list[User],
    workspace_id: str,
    actor: User,
    conversation_id: str,
    branch_id: str,
    node_id: str,
    text: str,
) -> list[Notice]:
    """Leave one notice per recipient. Caller commits."""
    excerpt = text.strip()
    if len(excerpt) > EXCERPT_CHARS:
        excerpt = excerpt[: EXCERPT_CHARS - 1].rstrip() + "…"

    out = []
    for u in recipients:
        n = Notice(
            user_id=u.id,
            workspace_id=workspace_id,
            kind="mention",
            actor_id=actor.id,
            actor_email=actor.email,
            conversation_id=conversation_id,
            branch_id=branch_id,
            node_id=node_id,
            excerpt=excerpt,
        )
        session.add(n)
        out.append(n)
    return out


def to_dict(n: Notice) -> dict:
    """Wire shape. Flat and denormalised, because the bell renders it directly
    and a notice that needed a second request to be readable would defeat the
    point of keeping it."""
    return {
        "id": n.id,
        "kind": n.kind,
        "workspace_id": n.workspace_id,
        "conversation_id": n.conversation_id,
        "branch_id": n.branch_id,
        "node_id": n.node_id,
        "actor_email": n.actor_email,
        "excerpt": n.excerpt,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "read": n.read_at is not None,
    }
