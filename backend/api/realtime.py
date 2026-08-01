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
    """Unique online users in a workspace (one entry even with several tabs).

    `viewing` is the branch the user has open right now (client-reported, see
    the read loop) — with several tabs, any tab that *is* viewing a branch wins
    over an idle one, so the Map's presence dot doesn't flicker off when a
    second tab opens.

    `drafting_conversation` is the shared conversation this user is composing a
    question in right now, and `drafting_match` is the id of a thread their
    draft already overlaps. Ids only, never the draft text and never a title:
    each recipient resolves the id against its own RBAC-scoped conversation
    list, so a thread the reader cannot see stays a bare id they render nothing
    for. See the read loop for the visibility gate on the drafting side.
    """
    seen: dict[str, dict] = {}
    for info in _rooms.get(workspace_id, {}).values():
        prev = seen.get(info["user_id"])
        entry = {
            "user_id": info["user_id"],
            "email": info["email"],
            "viewing": info.get("viewing"),
            "viewing_conversation": info.get("viewing_conversation"),
            "drafting_conversation": info.get("drafting_conversation"),
            "drafting_match": info.get("drafting_match"),
        }
        if entry["viewing"] is None and prev and prev["viewing"] is not None:
            entry["viewing"] = prev["viewing"]
            entry["viewing_conversation"] = prev["viewing_conversation"]
        # a tab that is actively drafting wins over an idle one, same as viewing
        if entry["drafting_conversation"] is None and prev and prev["drafting_conversation"]:
            entry["drafting_conversation"] = prev["drafting_conversation"]
            entry["drafting_match"] = prev["drafting_match"]
        seen[info["user_id"]] = entry
    return sorted(seen.values(), key=lambda u: u["email"])


async def _is_shared_conversation(workspace_id: str, conversation_id: str) -> bool:
    """Is this a shared thread of this workspace? Gate for the drafting signal.

    The client reports what it is drafting in, and a client can lie, so the
    server decides whether that fact may enter the roster at all. A private
    thread never announces itself.

    Reads through the conversation store rather than the ORM directly, so the
    gate holds for whichever store is configured — the same source of truth the
    HTTP routes use for every other visibility decision. Imported inside the
    function because the conversation router imports this module.
    """
    from .conversation.router import _store

    conv = await _store.get_conversation(conversation_id)
    return bool(
        conv and conv.workspace_id == workspace_id and conv.visibility == "shared"
    )


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
        # The read loop keeps the connection alive (ping/pong for proxies) and
        # accepts one client-reported fact: which branch this user is viewing
        # (`{"kind": "viewing", "branch_id": ...|null}`), folded into presence
        # so the Map can put live dots on the branches teammates have open.
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_text(json.dumps({"kind": "pong"}))
                continue
            try:
                msg = json.loads(text)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("kind") == "viewing":
                branch_id = msg.get("branch_id")
                conv_id = msg.get("conversation_id")
                info = _rooms[workspace_id][ws]
                info["viewing"] = branch_id if isinstance(branch_id, str) else None
                info["viewing_conversation"] = (
                    conv_id if isinstance(conv_id, str) and info["viewing"] else None
                )
                await _broadcast_presence(workspace_id)
            elif isinstance(msg, dict) and msg.get("kind") == "drafting":
                # "Someone is composing a question here, and it overlaps that
                # thread." Two ids and a boolean — no draft text is ever sent,
                # so the room learns that work is happening without reading
                # what has not been said yet.
                info = _rooms[workspace_id][ws]
                conv_id = msg.get("conversation_id")
                active = bool(msg.get("active")) and isinstance(conv_id, str)
                if active and conv_id != info.get("_drafting_checked"):
                    # One DB read per conversation per socket, not per keystroke:
                    # the client debounces, and the answer cannot change while
                    # the same thread stays on screen.
                    info["_drafting_ok"] = await _is_shared_conversation(
                        workspace_id, conv_id
                    )
                    info["_drafting_checked"] = conv_id
                allowed = active and info.get("_drafting_ok")
                match_id = msg.get("match_conversation_id")
                new_conv = conv_id if allowed else None
                new_match = match_id if allowed and isinstance(match_id, str) else None
                if (new_conv, new_match) != (
                    info.get("drafting_conversation"),
                    info.get("drafting_match"),
                ):
                    info["drafting_conversation"] = new_conv
                    info["drafting_match"] = new_match
                    await _broadcast_presence(workspace_id)
    except WebSocketDisconnect:
        pass
    finally:
        _rooms[workspace_id].pop(ws, None)
        await _broadcast_presence(workspace_id)
