"""The bell, made to outlast the tab.

What the bell held before this was a Zustand store: a teammate's run finishing,
a thread concluding, kept in the page's memory. Reload and the workspace had
never told you anything. That is a strange thing for a product whose claim is
that a team's thinking survives — the one surface that addressed a *person* was
the only one that forgot.

These endpoints are deliberately small. A notice is created by the thing that
caused it (see `api/mentions.py`), read here, and marked seen here. There is no
"delete": a notice you have read stops being unread and ages out of the list on
its own, and offering a delete would invite the reader to tidy away the one
record that says somebody asked them for something.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..mentions import to_dict
from ..models import Notice, User, _now

router = APIRouter(prefix="/api", tags=["notices"])

# The bell shows a recent window, not an archive. Someone returning after a
# month wants the last few things, and a bell that paginates is a mailbox.
LIMIT = 50


@router.get("/notices")
async def list_notices(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Your notices, newest first.

    Scoped to the caller by `user_id` and nothing else — a notice is addressed
    to a person, so there is no workspace filter to get wrong. Switching
    workspaces does not hide a mention from another one, which is deliberate:
    being asked something is not less urgent because you happen to be looking
    somewhere else.
    """
    rows = (
        await session.execute(
            select(Notice)
            .where(Notice.user_id == user.id)
            .order_by(Notice.created_at.desc())
            .limit(LIMIT)
        )
    ).scalars().all()
    return {"notices": [to_dict(n) for n in rows]}


@router.post("/notices/read")
async def mark_read(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Mark everything currently unread as seen.

    All-or-nothing on purpose: the bell marks read when it is opened, which is
    the moment the reader has in fact seen the list. Per-notice acknowledgement
    would be a to-do list, and a to-do list is a different product decision
    than a bell.
    """
    await session.execute(
        update(Notice)
        .where(Notice.user_id == user.id, Notice.read_at.is_(None))
        .values(read_at=_now())
    )
    await session.commit()
    return {"ok": True}
