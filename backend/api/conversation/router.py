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

from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from uuid import uuid4

from ..config import settings
from ..db import SessionLocal, get_session
from ..deps import get_current_user, get_membership
from ..errors import api_error
from ..models import ROLE_COLLABORATOR, ROLE_RANK, User
from ..prompts.store import PromptStore
from ..providers import get_provider
from . import engine
from .context import ReferenceBlock
from .deep_reasoning import DeepReasoningProducer, build_ouroboros_graph
from .events import to_dict, to_sse
from .producer import ChatProducer
from .store import DbStore

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Durable persistence: conversations/branches/nodes survive restarts. The engine
# is unchanged by this swap — it only ever sees the `ConversationStore` Protocol.
_store = DbStore(SessionLocal)
_prompts = PromptStore(SessionLocal)


class CreateConversation(BaseModel):
    workspace_id: str
    title: str = "Untitled"
    visibility: str = "shared"


class SendMessage(BaseModel):
    prompt: str


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
    return {"conversation_id": conv.id, "branch_id": conv.default_branch_id}


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

    lines = [f"# {conv.title}", f"_branch: {br.name} · {len(nodes)} nodes_", ""]
    for n in nodes:
        who = "Helix" if n.role == "assistant" else (n.author_id or "user")
        lines.append(f"**{who}**")
        lines.append("")
        lines.append(n.content)
        lines.append("")
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


@router.post("/{conversation_id}/fork")
async def fork_branch(
    conversation_id: str,
    body: ForkBranch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Fork a new branch off any node — O(1), no history copied (algorithm A1)."""
    await _require_conversation(conversation_id, user, session, ROLE_COLLABORATOR)
    try:
        branch = await _store.create_branch(
            conversation_id=conversation_id, from_node_id=body.from_node_id, name=body.name
        )
    except KeyError:
        raise api_error(404, "not_found", "node not found")
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
    return {"items": await _reference_summaries(conversation_id)}


@router.delete("/{conversation_id}/references/{referenced_conversation_id}")
async def remove_reference(
    conversation_id: str,
    referenced_conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Unlink a referenced conversation (idempotent)."""
    await _require_conversation(conversation_id, user, session, ROLE_COLLABORATOR)
    await _store.remove_reference(
        conversation_id=conversation_id,
        referenced_conversation_id=referenced_conversation_id,
    )
    return {"items": await _reference_summaries(conversation_id)}


@router.post("/{branch_id}/messages")
async def send_message(
    branch_id: str,
    body: SendMessage,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stream one turn as SSE: user_node -> token* -> assistant_node -> [DONE]."""
    branch, _conv = await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)

    references = await _resolve_reference_blocks(branch.conversation_id)
    producer = ChatProducer(get_provider(), references=references)

    async def event_stream():
        async for event in engine.send(
            store=_store,
            producer=producer,
            branch_id=branch_id,
            prompt=body.prompt,
            author_id=user.id,
        ):
            yield to_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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

    references = await _resolve_reference_blocks(branch.conversation_id)
    producer = ChatProducer(get_provider(), references=references)

    async def event_stream():
        async for event in engine.send(
            store=_store,
            producer=producer,
            branch_id=branch_id,
            prompt=prompt.body,
            author_id=user.id,
        ):
            yield to_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{branch_id}/deep")
async def escalate_deep_reasoning(
    branch_id: str,
    body: SendMessage,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Escalate one turn to Deep Reasoning (Ouroboros), streamed as SSE.

    Same engine, same branch, same event contract as `messages` — only the
    producer differs ("one mount, two producers"). Emits the richer trace:
    user_node -> (step | budget)* -> token (final answer) -> complete ->
    assistant_node -> [DONE].
    """
    await _require_branch(branch_id, user, session, ROLE_COLLABORATOR)
    if not settings.groq_api_key:
        raise api_error(503, "deep_reasoning_unavailable", "GROQ_API_KEY is not configured")

    graph, graph_config, make_inputs, usage_reader = build_ouroboros_graph(
        thread_id=uuid4().hex,
        groq_api_key=settings.groq_api_key,
        groq_model=settings.deep_reasoning_model,
        mode=settings.deep_reasoning_mode,
        adaptive=settings.deep_reasoning_adaptive,
        compute_budget=settings.deep_reasoning_compute_budget,
        stability_threshold=settings.deep_reasoning_stability_threshold,
        confidence_threshold=settings.deep_reasoning_confidence_threshold,
    )
    producer = DeepReasoningProducer(
        graph=graph,
        graph_config=graph_config,
        make_inputs=make_inputs,
        usage_reader=usage_reader,
        token_budget=settings.deep_reasoning_token_budget,
    )

    async def event_stream():
        async for event in engine.send(
            store=_store,
            producer=producer,
            branch_id=branch_id,
            prompt=body.prompt,
            author_id=user.id,
        ):
            yield to_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
