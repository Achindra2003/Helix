"""HTTP surface for the conversation engine (E2).

Thin wiring: it owns the DB-backed store and the configured provider, then
streams `engine.send` as Server-Sent Events.

Every route is auth-gated server-side (FR-3 / NFR-5): identity comes from the
JWT — never from client-supplied ids — and each request is checked against the
caller's workspace membership. Reads need any membership (Observer included);
writes (send / fork / deep / references / insert) need Collaborator or higher.
Private conversations are visible to their author only, and non-membership is
reported as 404 so tenants can't probe for each other's resources.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from uuid import uuid4

from ..config import settings
from ..db import SessionLocal, get_session
from ..deps import get_current_user, get_membership
from ..errors import api_error
from ..models import ROLE_COLLABORATOR, ROLE_OWNER, ROLE_RANK, User
from .. import realtime
from ..prompts.store import PromptStore
from ..provider_settings import ResolvedProvider, build_chat_provider, resolve
from ..models import WorkspaceSettings
from . import engine
from .context import ReferenceBlock
from .deep_reasoning import DeepReasoningProducer, build_ouroboros_graph
from .embeddings import EmbeddingIndex
from ..documents.service import DocumentIndex
from .events import DeepRunRegistered, to_dict, to_sse
from .models import DeepRunRow
from .run_log import DeepRunRecorder
from .runs import RunHandle, RunManager
from .producer import ChatProducer
from .store import DbStore

router = APIRouter(prefix="/conversations", tags=["conversations"])

# The retrieval substrate: every persisted node gets an embedding row (written
# fire-and-forget off the hot path; backfilled lazily on first retrieval), and
# semantic recall reads those instead of re-embedding a thread per send.
_embeddings = EmbeddingIndex(SessionLocal)

# File grounding: workspace documents, retrieved per turn when relevant.
_documents = DocumentIndex(SessionLocal)


def _grounder_for(workspace_id: str):
    """A Grounder bound to one workspace (see producer.Grounder)."""

    async def grounder(history):
        return await _documents.grounding_block(workspace_id, history)

    return grounder

# Durable persistence: conversations/branches/nodes survive restarts. The engine
# is unchanged by this swap — it only ever sees the `ConversationStore` Protocol.
_store = DbStore(SessionLocal, on_node=_embeddings.ensure_soon)
_prompts = PromptStore(SessionLocal)


class CreateConversation(BaseModel):
    workspace_id: str
    title: str = "Untitled"
    visibility: str = "shared"


class SendMessage(BaseModel):
    prompt: str


class DeepRequest(BaseModel):
    prompt: str
    # Guided mode: the run pauses at a steer checkpoint between refinement
    # cycles; the client resumes it (with optional guidance) via
    # POST /conversations/deep/runs/{run_id}/steer.
    steerable: bool = False


class SteerRequest(BaseModel):
    guidance: str = ""  # empty = "continue as you were"


class ForkBranch(BaseModel):
    from_node_id: str
    name: str = "branch"


class InsertPrompt(BaseModel):
    prompt_id: str


class AddReference(BaseModel):
    referenced_conversation_id: str


# --- RBAC helpers -----------------------------------------------------------


async def _require_membership(
    workspace_id: str, user: User, session: AsyncSession, min_role: str | None = None
):
    """The caller's membership in `workspace_id` (404 if none), optionally
    requiring at least `min_role` (403 below it)."""
    membership = await get_membership(workspace_id, user, session)
    if min_role is not None and ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
        raise api_error(403, "forbidden", f"Requires {min_role} role or higher.")
    return membership


async def _require_conversation(
    conversation_id: str,
    user: User,
    session: AsyncSession,
    min_role: str | None = None,
):
    """The conversation, once the caller may act on it.

    Order matters: membership is checked before the private-visibility rule, and
    both failures read as 404 — a caller outside the workspace (or outside a
    private thread) can't distinguish "hidden" from "nonexistent".
    """
    conv = await _store.get_conversation(conversation_id)
    if conv is None:
        raise api_error(404, "not_found", "conversation not found")
    await _require_membership(conv.workspace_id, user, session, min_role)
    if conv.visibility == "private" and conv.author_id != user.id:
        raise api_error(404, "not_found", "conversation not found")
    return conv


async def _require_branch(
    branch_id: str,
    user: User,
    session: AsyncSession,
    min_role: str | None = None,
):
    """The branch + its conversation, once the caller may act on them."""
    branch = await _store.get_branch(branch_id)
    if branch is None:
        raise api_error(404, "not_found", "branch not found")
    conv = await _require_conversation(branch.conversation_id, user, session, min_role)
    return branch, conv


def _streamed_run(conv, branch_id: str, user: User, gen) -> StreamingResponse:
    """Stream a run as SSE while relaying each event to the workspace room.

    Only *shared* conversations are relayed — a private thread's turns must
    never leave its author's own stream. The author is excluded from the
    relay (their SSE already carries every event); teammates watching the
    same branch see the turn appear token-by-token.
    """
    shared = conv.visibility == "shared"

    async def stream():
        async for event in gen:
            yield to_sse(event)
            if shared:
                await realtime.broadcast(
                    conv.workspace_id,
                    {
                        "kind": "run_event",
                        "workspace_id": conv.workspace_id,
                        "conversation_id": conv.id,
                        "branch_id": branch_id,
                        "author_id": user.id,
                        "event": to_dict(event),
                    },
                    exclude_user=user.id,
                )

    return StreamingResponse(stream(), media_type="text/event-stream")


async def _resolve_reference_blocks(conversation_id: str) -> list[ReferenceBlock]:
    """Pull the *current* context of every conversation linked to `conversation_id`.

    Resolved fresh on each turn (live reference): for each linked conversation we
    read its default branch's history now, so updates in the source thread are seen
    on the next turn here. Dangling links (a deleted source) are skipped silently.
    """
    blocks: list[ReferenceBlock] = []
    for ref_id in await _store.list_reference_ids(conversation_id):
        ref_conv = await _store.get_conversation(ref_id)
        if ref_conv is None:
            continue
        history = await _store.get_history(ref_conv.default_branch_id)
        blocks.append(ReferenceBlock(title=ref_conv.title, history=history))
    return blocks


@router.post("")
async def create_conversation(
    body: CreateConversation,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _require_membership(body.workspace_id, user, session, ROLE_COLLABORATOR)
    conv = await _store.create_conversation(
        workspace_id=body.workspace_id,
        author_id=user.id,
        title=body.title,
        visibility=body.visibility,
    )
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "conversation.created",
                "workspace_id": conv.workspace_id,
                "conversation_id": conv.id,
                "title": conv.title,
            },
            exclude_user=user.id,
        )
    return {"conversation_id": conv.id, "branch_id": conv.default_branch_id}


class RenameConversation(BaseModel):
    title: str


async def _require_author_or_owner(conv, user: User, session: AsyncSession) -> None:
    """Rename/delete of a conversation belongs to its author, or an owner —
    the same split as documents (uploader-or-owner)."""
    membership = await get_membership(conv.workspace_id, user, session)
    if conv.author_id != user.id and membership.role != ROLE_OWNER:
        raise api_error(
            403, "forbidden", "Only the author or a workspace owner can do this."
        )


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: RenameConversation,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await _require_conversation(conversation_id, user, session, ROLE_COLLABORATOR)
    await _require_author_or_owner(conv, user, session)
    title = body.title.strip() or "Untitled"
    updated = await _store.rename_conversation(conversation_id, title)
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "conversation.updated",
                "workspace_id": conv.workspace_id,
                "conversation_id": conversation_id,
                "title": title,
            },
            exclude_user=user.id,
        )
    return {"conversation_id": conversation_id, "title": updated.title}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a conversation with its whole tree (branches, nodes, embeddings,
    reference links, run records). Author or owner only."""
    conv = await _require_conversation(conversation_id, user, session, ROLE_COLLABORATOR)
    await _require_author_or_owner(conv, user, session)
    removed = await _store.delete_conversation(conversation_id)
    await _embeddings.drop(removed)
    # Run records are written outside the store (DeepRunRecorder) — clean them
    # here so the archive can't point at a conversation that no longer exists.
    await session.execute(
        sa_delete(DeepRunRow).where(DeepRunRow.conversation_id == conversation_id)
    )
    await session.commit()
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "conversation.deleted",
                "workspace_id": conv.workspace_id,
                "conversation_id": conversation_id,
            },
            exclude_user=user.id,
        )
    return {"removed_nodes": len(removed)}


@router.get("")
async def list_conversations(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Conversations in a workspace, so the sidebar survives reloads.

    Visibility is scoped to the *authenticated* caller: shared conversations are
    returned to every member, a private one only to its author.
    """
    await _require_membership(workspace_id, user, session)
    convs = await _store.list_conversations(workspace_id, user.id)
    return {"items": [asdict(c) for c in convs]}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await _require_conversation(conversation_id, user, session)
    return asdict(conv)


@router.get("/{conversation_id}/branches")
async def list_branches(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The branch tree (client renders `parent_branch_id` links as Git-style lineage)."""
    await _require_conversation(conversation_id, user, session)
    branches = await _store.list_branches(conversation_id)
    return {"items": [asdict(b) for b in branches]}


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    branch: str,
    format: str = "md",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Export a branch's full history (root -> head) as Markdown or JSON (F9)."""
    conv = await _require_conversation(conversation_id, user, session)
    br = await _store.get_branch(branch)
    if br is None or br.conversation_id != conversation_id:
        raise api_error(404, "not_found", "branch not found")
    nodes = await _store.get_history(branch)
    stem = "".join(c if c.isalnum() else "-" for c in conv.title).strip("-") or "conversation"

    if format == "json":
        payload = {
            "conversation": asdict(conv),
            "branch": asdict(br),
            "nodes": [to_dict(n) for n in nodes],
        }
        return JSONResponse(
            content=payload,
            headers={"Content-Disposition": f'attachment; filename="{stem}.json"'},
        )

    # "Fair copy": a manuscript-styled rendering — title block, a rule, the
    # turns with authors resolved to emails, and a colophon footer.
    emails: dict[str, str] = {}

    async def _who(author_id: str | None) -> str:
        if author_id is None:
            return "Helix"
        if author_id not in emails:
            author = await session.get(User, author_id)
            emails[author_id] = author.email if author else author_id
        return emails[author_id]

    lines = [
        f"# {conv.title}",
        "",
        f"*a Helix conversation · branch “{br.name}” · {len(nodes)} nodes*",
        "",
        "---",
        "",
    ]
    for n in nodes:
        who = "Helix" if n.role == "assistant" else await _who(n.author_id)
        lines.append(f"**{who}**")
        lines.append("")
        lines.append(n.content)
        lines.append("")
    lines += [
        "---",
        "",
        f"❧ fair copy · exported from Helix on {date.today().isoformat()} ❧",
        "",
    ]
    return Response(
        content="\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{stem}.md"'},
    )


@router.get("/branches/{branch_id}/history")
async def get_history(
    branch_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The branch's full history (root -> head), walking across fork boundaries."""
    await _require_branch(branch_id, user, session)
    nodes = await _store.get_history(branch_id)
    return {"branch_id": branch_id, "nodes": [to_dict(n) for n in nodes]}


class RenameBranch(BaseModel):
    name: str


@router.patch("/branches/{branch_id}")
async def rename_branch(
    branch_id: str,
    body: RenameBranch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Rename a branch. Branches carry no author (they're shared structure),
    so any Collaborator may — same bar as forking one."""
    branch, conv = await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)
    name = body.name.strip() or "branch"
    updated = await _store.rename_branch(branch_id, name)
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "branch.updated",
                "workspace_id": conv.workspace_id,
                "conversation_id": conv.id,
                "branch_id": branch_id,
                "name": name,
            },
            exclude_user=user.id,
        )
    return {"branch_id": branch_id, "name": updated.name}


@router.delete("/branches/{branch_id}")
async def delete_branch(
    branch_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete an abandoned fork branch (its own nodes only — inherited context
    belongs to ancestors). Refused for main and for anything forked-from."""
    branch, conv = await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)
    try:
        removed = await _store.delete_branch(branch_id)
    except KeyError:
        raise api_error(404, "not_found", "branch not found")
    except ValueError as exc:
        raise api_error(409, "conflict", str(exc))
    await _embeddings.drop(removed)
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "branch.deleted",
                "workspace_id": conv.workspace_id,
                "conversation_id": conv.id,
                "branch_id": branch_id,
            },
            exclude_user=user.id,
        )
    return {"removed_nodes": len(removed)}


@router.post("/{conversation_id}/fork")
async def fork_branch(
    conversation_id: str,
    body: ForkBranch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Fork a new branch off any node — O(1), no history copied (algorithm A1)."""
    conv = await _require_conversation(conversation_id, user, session, ROLE_COLLABORATOR)
    try:
        branch = await _store.create_branch(
            conversation_id=conversation_id, from_node_id=body.from_node_id, name=body.name
        )
    except KeyError:
        raise api_error(404, "not_found", "node not found")
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "branch.created",
                "workspace_id": conv.workspace_id,
                "conversation_id": conversation_id,
                "branch_id": branch.id,
                "name": branch.name,
            },
            exclude_user=user.id,
        )
    return {"branch_id": branch.id, "fork_node_id": branch.fork_node_id, "name": branch.name}


async def _reference_summaries(conversation_id: str) -> list[dict]:
    """The linked conversations as {id, title}, skipping any since deleted."""
    out: list[dict] = []
    for ref_id in await _store.list_reference_ids(conversation_id):
        ref = await _store.get_conversation(ref_id)
        if ref is not None:
            out.append({"id": ref.id, "title": ref.title})
    return out


@router.get("/{conversation_id}/references")
async def list_references(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Conversations whose live context is folded into this one's turns."""
    await _require_conversation(conversation_id, user, session)
    return {"items": await _reference_summaries(conversation_id)}


@router.post("/{conversation_id}/references", status_code=201)
async def add_reference(
    conversation_id: str,
    body: AddReference,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Link another *shared* conversation in the same workspace as live context.

    Cross-thread grounding (not a fork): the linked thread's current context is
    pulled into this conversation's replies. Guards keep it sane — the target must
    exist, be in the same workspace, be `shared`, and not be this conversation.
    """
    conv = await _require_conversation(conversation_id, user, session, ROLE_COLLABORATOR)
    target_id = body.referenced_conversation_id
    if target_id == conversation_id:
        raise api_error(400, "bad_request", "a conversation cannot reference itself")
    target = await _store.get_conversation(target_id)
    if target is None:
        raise api_error(404, "not_found", "referenced conversation not found")
    if target.workspace_id != conv.workspace_id:
        raise api_error(400, "bad_request", "can only reference threads in this workspace")
    if target.visibility != "shared":
        raise api_error(403, "forbidden", "only shared conversations can be referenced")
    await _store.add_reference(
        conversation_id=conversation_id, referenced_conversation_id=target_id
    )
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "references.updated",
                "workspace_id": conv.workspace_id,
                "conversation_id": conversation_id,
            },
            exclude_user=user.id,
        )
    return {"items": await _reference_summaries(conversation_id)}


@router.delete("/{conversation_id}/references/{referenced_conversation_id}")
async def remove_reference(
    conversation_id: str,
    referenced_conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Unlink a referenced conversation (idempotent)."""
    conv = await _require_conversation(conversation_id, user, session, ROLE_COLLABORATOR)
    await _store.remove_reference(
        conversation_id=conversation_id,
        referenced_conversation_id=referenced_conversation_id,
    )
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "references.updated",
                "workspace_id": conv.workspace_id,
                "conversation_id": conversation_id,
            },
            exclude_user=user.id,
        )
    return {"items": await _reference_summaries(conversation_id)}


async def _workspace_provider(workspace_id: str, session: AsyncSession) -> ResolvedProvider:
    """The workspace's resolved LLM settings (BYO key), or a clear 503.

    A missing key must fail *before* the user node persists and the SSE stream
    opens — a dead composer with a reason beats a torn stream.
    """
    resolved = resolve(await session.get(WorkspaceSettings, workspace_id))
    if resolved.missing_key:
        raise api_error(
            503,
            "provider_unconfigured",
            "No LLM API key is configured for this workspace — the owner can add "
            "one under workspace settings → Provider.",
        )
    return resolved


@router.delete("/{branch_id}/messages/last")
async def delete_last_message(
    branch_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete (or, from the UI, "edit and resend") the trailing message you
    authored — and its assistant reply, if one landed. Safe only when nothing
    has forked from either node; append-only history stays intact for anyone
    who already branched off it (§3 of the completion plan)."""
    branch, conv = await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)
    try:
        removed_ids = await _store.delete_last_turn(branch_id=branch_id, user_id=user.id)
    except KeyError:
        raise api_error(404, "not_found", "nothing to delete on this branch")
    except PermissionError:
        raise api_error(403, "forbidden", "only the author may remove their message")
    except ValueError:
        raise api_error(
            409, "conflict",
            "can't remove this message — a branch has already forked from it",
        )
    await _embeddings.drop(removed_ids)
    if conv.visibility == "shared":
        await realtime.broadcast(
            conv.workspace_id,
            {
                "kind": "messages.deleted",
                "workspace_id": conv.workspace_id,
                "conversation_id": conv.id,
                "branch_id": branch_id,
                "node_ids": removed_ids,
            },
            exclude_user=user.id,
        )
    return {"removed_ids": removed_ids}


@router.post("/{branch_id}/messages")
async def send_message(
    branch_id: str,
    body: SendMessage,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stream one turn as SSE: user_node -> token* -> assistant_node -> [DONE]."""
    branch, conv = await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)

    resolved = await _workspace_provider(conv.workspace_id, session)
    references = await _resolve_reference_blocks(branch.conversation_id)
    producer = ChatProducer(
        build_chat_provider(resolved),
        references=references,
        recaller=_embeddings.recall_block,
        grounder=_grounder_for(conv.workspace_id),
    )

    gen = engine.send(
        store=_store,
        producer=producer,
        branch_id=branch_id,
        prompt=body.prompt,
        author_id=user.id,
    )
    return _streamed_run(conv, branch_id, user, gen)


@router.post("/{branch_id}/messages/from-prompt")
async def send_from_prompt(
    branch_id: str,
    body: InsertPrompt,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Insert path: run a saved library prompt's body as a chat turn on this branch.

    Proves the library is *reusable* — the same winning prompt can drive a turn in
    any conversation. Streams the same SSE contract as `messages`.
    """
    branch, conv = await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)
    prompt = await _prompts.get(body.prompt_id)
    if prompt is None or prompt.workspace_id != conv.workspace_id:
        raise api_error(404, "not_found", "prompt not found")

    resolved = await _workspace_provider(conv.workspace_id, session)
    references = await _resolve_reference_blocks(branch.conversation_id)
    producer = ChatProducer(
        build_chat_provider(resolved),
        references=references,
        recaller=_embeddings.recall_block,
        grounder=_grounder_for(conv.workspace_id),
    )

    gen = engine.send(
        store=_store,
        producer=producer,
        branch_id=branch_id,
        prompt=prompt.body,
        author_id=user.id,
    )
    return _streamed_run(conv, branch_id, user, gen)


# Deep runs execute server-side in background tasks (they survive a dropped
# client); the manager owns launch/subscribe/steer/kill and the workspace
# concurrency queue. In-process, like the realtime rooms.
_runs = RunManager(
    per_workspace=settings.deep_runs_per_workspace,
    retention_s=settings.deep_run_retention_s,
)


def _subscription(handle, *, after: int = 0) -> StreamingResponse:
    """SSE that replays the run's log from `after`, then follows live.

    Unlike the old in-request streaming, cancelling this response detaches the
    subscriber only — the driver task keeps running (the WS relay to teammates
    happens there too, not here).
    """

    async def stream():
        async for event in _runs.stream(handle, after=after):
            yield to_sse(event)

    return StreamingResponse(stream(), media_type="text/event-stream")


async def _require_run(
    run_id: str, user: User, session: AsyncSession, min_role: str | None = None
):
    """The live run handle, once the caller may act on its conversation."""
    handle = _runs.get(run_id)
    if handle is None:
        raise api_error(404, "not_found", "deep run not found (finished or expired)")
    await _require_conversation(handle.conversation_id, user, session, min_role)
    return handle


@router.post("/{branch_id}/deep")
async def escalate_deep_reasoning(
    branch_id: str,
    body: DeepRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Escalate one turn to Deep Reasoning (Ouroboros), streamed as SSE.

    Same engine, same branch, same event contract as `messages` — only the
    producer differs ("one mount, two producers"). Emits the richer trace:
    deep_run (the run_id handle) -> user_node -> (step | budget)* -> token
    (final answer) -> complete -> assistant_node -> [DONE].

    The run itself executes server-side: closing this stream does not stop it
    (reconnect via GET /conversations/deep/runs/{run_id}/stream; stop it for
    real via POST .../kill). At most `deep_runs_per_workspace` run at once —
    a `queued` frame says the run is waiting for a slot.

    With `steerable: true` the run is *guided*: it pauses at a steer
    checkpoint between refinement cycles (`waiting` ends the stream, no
    assistant node yet) and resumes via POST /conversations/deep/runs/
    {run_id}/steer — as many times as it pauses.
    """
    branch, conv = await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)
    # Deep Reasoning runs on Groq: the workspace's own Groq key wins, the
    # server-wide key is the fallback (self-host), no key at all is a clear 503.
    resolved = resolve(await session.get(WorkspaceSettings, conv.workspace_id))
    if not resolved.deep_groq_key:
        raise api_error(
            503,
            "deep_reasoning_unavailable",
            "Deep Reasoning needs a Groq API key — the workspace owner can add "
            "one under workspace settings → Provider.",
        )

    run_id = uuid4().hex
    handle_box: list = []  # producer's should_stop closes over the handle

    graph, graph_config, make_inputs, usage_reader = build_ouroboros_graph(
        thread_id=uuid4().hex,
        groq_api_key=resolved.deep_groq_key,
        groq_model=resolved.resolved_deep_model,
        mode=settings.deep_reasoning_mode,
        adaptive=settings.deep_reasoning_adaptive,
        compute_budget=settings.deep_reasoning_compute_budget,
        stability_threshold=settings.deep_reasoning_stability_threshold,
        confidence_threshold=settings.deep_reasoning_confidence_threshold,
        adaptive_steer=body.steerable,
        allow_research=settings.deep_reasoning_allow_research,
    )
    producer = DeepReasoningProducer(
        graph=graph,
        graph_config=graph_config,
        make_inputs=make_inputs,
        usage_reader=usage_reader,
        token_budget=settings.deep_reasoning_token_budget,
        deadline_s=settings.deep_reasoning_deadline_s,
        should_stop=lambda: bool(handle_box and handle_box[0].kill_requested),
        grounder=_grounder_for(conv.workspace_id),
    )
    # Every deep run leaves a durable record (question, signals, outcome, compact
    # trace) — the monitor is ephemeral; DeepRunRow is what you inspect tomorrow.
    recorder = DeepRunRecorder(
        run_id=run_id,
        workspace_id=conv.workspace_id,
        conversation_id=conv.id,
        branch_id=branch_id,
        author_id=user.id,
        session_factory=SessionLocal,
        model=resolved.resolved_deep_model,
        provenance={
            "mode": settings.deep_reasoning_mode,
            "adaptive": settings.deep_reasoning_adaptive,
            "steerable": body.steerable,
            "compute_budget": settings.deep_reasoning_compute_budget,
            # The *resolved* threshold (auto-calibration applied), from the
            # graph build -- not the possibly-None configured value.
            "stability_threshold": (graph_config.get("metadata") or {}).get(
                "stability_threshold"
            ),
            "confidence_threshold": settings.deep_reasoning_confidence_threshold,
            "token_budget": settings.deep_reasoning_token_budget,
            "deadline_s": settings.deep_reasoning_deadline_s,
            "embedder": _embeddings.version,
            "provider_source": resolved.source,  # workspace BYO key vs server
        },
    )
    # ResumableRun serves both kinds: a non-steerable graph simply never pauses.
    run = engine.ResumableRun(store=_store, producer=producer, branch_id=branch_id)
    handle = RunHandle(
        run_id=run_id,
        workspace_id=conv.workspace_id,
        conversation_id=conv.id,
        branch_id=branch_id,
        author_id=user.id,
        shared=conv.visibility == "shared",
        run=run,
        recorder=recorder,
    )
    handle_box.append(handle)
    handle.events.append(DeepRunRegistered(run_id=run_id))

    def start():
        return run.start(prompt=body.prompt, author_id=user.id)

    _runs.launch(handle=handle, start=start)
    return _subscription(handle)


@router.post("/deep/runs/{run_id}/steer")
async def steer_deep_run(
    run_id: str,
    body: SteerRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Resume a paused guided run, injecting optional human guidance (FR-11).

    Any Collaborator in the workspace may steer — a paused run on a shared
    thread is a team decision point, not a private lock. Streams the
    continuation with the same event contract; pauses again at the next
    checkpoint unless the run converges or exhausts its budget.
    """
    handle = await _require_run(run_id, user, session, ROLE_COLLABORATOR)
    run = handle.run
    if handle.status != "paused" or not run.paused:
        raise api_error(409, "conflict", "run is not paused for steer")
    handle.recorder.note_steer(body.guidance)

    resume_from = handle.seq  # stream only the continuation, like the old segments
    _runs.steer(handle, lambda: run.steer(body.guidance))
    return _subscription(handle, after=resume_from)


@router.get("/deep/runs/{run_id}/stream")
async def reconnect_deep_run(
    run_id: str,
    after: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """(Re)attach to a live run's stream: replay events from `after`, follow live.

    The recovery path the background model buys: a dropped connection, a page
    reload, or a second device can pick the run back up mid-flight. Any member
    who can read the conversation may watch.
    """
    handle = await _require_run(run_id, user, session)
    return _subscription(handle, after=max(0, after))


@router.get("/deep/runs/{run_id}/status")
async def deep_run_status(
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Cheap poll: where is this run right now (without opening a stream)?"""
    handle = await _require_run(run_id, user, session)
    return {
        "run_id": handle.run_id,
        "status": handle.status,
        "seq": handle.seq,
        "queue_position": _runs.queue_position(handle),
    }


@router.post("/deep/runs/{run_id}/kill")
async def kill_deep_run(
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stop a run for real (closing the stream no longer does): cooperative
    between events when running, immediate when queued or paused. Collaborator+,
    same as starting one — a runaway run burns the workspace's own key."""
    handle = await _require_run(run_id, user, session, ROLE_COLLABORATOR)
    _runs.kill(handle)
    return {"run_id": handle.run_id, "status": handle.status}


@router.get("/{conversation_id}/deep/runs")
async def list_deep_runs(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The conversation's persisted deep-run records, newest first (any member
    who can read the conversation can read its run history)."""
    await _require_conversation(conversation_id, user, session)
    result = await session.execute(
        select(DeepRunRow)
        .where(DeepRunRow.conversation_id == conversation_id)
        .order_by(DeepRunRow.created_at.desc())
        .limit(50)
    )
    return {
        "items": [
            {
                "id": r.id,
                "question": r.question[:200],
                "status": r.status,
                "stop_reason": r.stop_reason,
                "depth": r.depth,
                "stability": r.stability,
                "confidence": r.confidence,
                "tokens_used": r.tokens_used,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in result.scalars()
        ]
    }


@router.get("/deep/runs/{run_id}/record")
async def get_deep_run_record(
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """One run's full record, trace included — the post-hoc debugging view."""
    row = await session.get(DeepRunRow, run_id)
    if row is None:
        raise api_error(404, "not_found", "deep run record not found")
    await _require_conversation(row.conversation_id, user, session)
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "branch_id": row.branch_id,
        "author_id": row.author_id,
        "question": row.question,
        "answer": row.answer,
        "status": row.status,
        "stop_reason": row.stop_reason,
        "depth": row.depth,
        "stability": row.stability,
        "confidence": row.confidence,
        "tokens_used": row.tokens_used,
        "duration_ms": row.duration_ms,
        "trace": json.loads(row.trace),
        "model": row.model or "",
        "provenance": json.loads(row.provenance or "{}"),
        "created_at": row.created_at.isoformat(),
    }
