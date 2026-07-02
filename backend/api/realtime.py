"""Workspace realtime rooms — presence + live fan-out (FR-5, NFR-1/7).

One WebSocket room per workspace. Members connect at
``/ws/workspaces/{workspace_id}?token=<jwt>`` (browsers can't set headers on a
WebSocket, so the JWT rides a query param and is verified exactly like the
Authorization header). The room then does two jobs:

- **Presence** — every join/leave broadcasts the current roster, so the UI can
  show who is actually here, live.
- **Fan-out** — the HTTP routes call :func:`broadcast` when something changes
  (a turn streaming on a shared thread, a new conversation, a fork, a saved
  prompt), and every *other* member's client updates without a refresh. The
  sender is excluded: their own SSE stream / mutation response already carries
  the change.

Scale note (NFR-4): rooms are in-process dicts — exactly right for one API
process. Multi-process deployment swaps this module for a Redis pub/sub with
the same two functions; nothing above this seam changes.
"""
from __future__ import annotations

import json
from collections import defaultdict

import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from .db import SessionLocal
from .models import Membership, User
from .security import decode_token

router = APIRouter(tags=["realtime"])

# workspace_id -> { WebSocket: {"user_id", "email"} }
_rooms: dict[str, dict[WebSocket, dict]] = defaultdict(dict)


def roster(workspace_id: str) -> list[dict]:
    """Unique online users in a workspace (one entry even with several tabs)."""
    seen: dict[str, dict] = {}
    for info in _rooms.get(workspace_id, {}).values():
        seen[info["user_id"]] = {"user_id": info["user_id"], "email": info["email"]}
    return sorted(seen.values(), key=lambda u: u["email"])


async def broadcast(
    workspace_id: str, payload: dict, exclude_user: str | None = None
) -> None:
    """Send `payload` to every room member (minus `exclude_user`'s sockets).

    Never raises: a dead socket is dropped, not propagated — realtime is an
    overlay, and a broken listener must not break the sender's request.
    """
    room = _rooms.get(workspace_id)
    if not room:
        return
    message = json.dumps(payload)
    for ws, info in list(room.items()):
        if exclude_user is not None and info["user_id"] == exclude_user:
            continue
        try:
            await ws.send_text(message)
        except Exception:
            room.pop(ws, None)


async def _broadcast_presence(workspace_id: str) -> None:
    await broadcast(
        workspace_id,
        {"kind": "presence", "workspace_id": workspace_id, "users": roster(workspace_id)},
    )


@router.websocket("/ws/workspaces/{workspace_id}")
async def workspace_room(
    ws: WebSocket, workspace_id: str, token: str = Query(default="")
):
    # Same identity + membership gate as the HTTP routes (custom close codes
    # live in the 4000-4999 app range).
    try:
        user_id = decode_token(token)
    except pyjwt.PyJWTError:
        await ws.close(code=4401)
        return
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        member = user and await session.scalar(
            select(Membership).where(
                Membership.workspace_id == workspace_id,
                Membership.user_id == user.id,
            )
        )
    if not member:
        await ws.close(code=4403)
        return

    await ws.accept()
    _rooms[workspace_id][ws] = {"user_id": user.id, "email": user.email}
    await _broadcast_presence(workspace_id)

    try:
        # The server never *needs* client messages; this read loop keeps the
        # connection alive and answers pings so proxies don't idle it out.
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_text(json.dumps({"kind": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        _rooms[workspace_id].pop(ws, None)
        await _broadcast_presence(workspace_id)
