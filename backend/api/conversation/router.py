"""HTTP surface for the conversation engine (E2).

Thin wiring: it owns a process-level `InMemoryStore` and the stub/configured
provider, then streams `engine.send` as Server-Sent Events. The DB-backed store
swaps in here as a one-line change (the engine is untouched), and auth/RBAC
gating arrives with the DB + escalation buckets — this slice exists to prove the
streaming pipeline end-to-end (E5 smoke).
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from uuid import uuid4

from ..config import settings
from ..db import SessionLocal
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
    workspace_id: str = "w1"
    author_id: str = "u1"
    title: str = "Untitled"
    visibility: str = "shared"


class SendMessage(BaseModel):
    prompt: str
    author_id: str = "u1"


class ForkBranch(BaseModel):
    from_node_id: str
    name: str = "branch"


class InsertPrompt(BaseModel):
    prompt_id: str
    author_id: str = "u1"


class AddReference(BaseModel):
    referenced_conversation_id: str


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
async def create_conversation(body: CreateConversation):
    conv = await _store.create_conversation(
        workspace_id=body.workspace_id,
        author_id=body.author_id,
        title=body.title,
        visibility=body.visibility,
    )
    return {"conversation_id": conv.id, "branch_id": conv.default_branch_id}


@router.get("")
async def list_conversations(workspace_id: str, viewer_id: str | None = None):
    """Conversations in a workspace, so the sidebar survives reloads.

    `viewer_id` (the requesting user) scopes visibility: shared conversations are
    returned to everyone, but a private one only to its author. Omit it to list all.
    """
    convs = await _store.list_conversations(workspace_id, viewer_id)
    return {"items": [asdict(c) for c in convs]}


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = await _store.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "conversation not found"},
        )
    return asdict(conv)


@router.get("/{conversation_id}/branches")
async def list_branches(conversation_id: str):
    """The branch tree (client renders `parent_branch_id` links as Git-style lineage)."""
    if await _store.get_conversation(conversation_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "conversation not found"},
        )
    branches = await _store.list_branches(conversation_id)
    return {"items": [asdict(b) for b in branches]}


@router.get("/{conversation_id}/export")
async def export_conversation(conversation_id: str, branch: str, format: str = "md"):
    """Export a branch's full history (root -> head) as Markdown or JSON (F9)."""
    conv = await _store.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "conversation not found"},
        )
    br = await _store.get_branch(branch)
    if br is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "branch not found"}
        )
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
async def get_history(branch_id: str):
    """The branch's full history (root -> head), walking across fork boundaries."""
    if await _store.get_branch(branch_id) is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "branch not found"}
        )
    nodes = await _store.get_history(branch_id)
    return {"branch_id": branch_id, "nodes": [to_dict(n) for n in nodes]}


@router.post("/{conversation_id}/fork")
async def fork_branch(conversation_id: str, body: ForkBranch):
    """Fork a new branch off any node — O(1), no history copied (algorithm A1)."""
    if await _store.get_conversation(conversation_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "conversation not found"},
        )
    try:
        branch = await _store.create_branch(
            conversation_id=conversation_id, from_node_id=body.from_node_id, name=body.name
        )
    except KeyError:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "node not found"}
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
async def list_references(conversation_id: str):
    """Conversations whose live context is folded into this one's turns."""
    if await _store.get_conversation(conversation_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "conversation not found"},
        )
    return {"items": await _reference_summaries(conversation_id)}


@router.post("/{conversation_id}/references", status_code=201)
async def add_reference(conversation_id: str, body: AddReference):
    """Link another *shared* conversation in the same workspace as live context.

    Cross-thread grounding (not a fork): the linked thread's current context is
    pulled into this conversation's replies. Guards keep it sane — the target must
    exist, be in the same workspace, be `shared`, and not be this conversation.
    """
    conv = await _store.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "conversation not found"},
        )
    target_id = body.referenced_conversation_id
    if target_id == conversation_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_request", "message": "a conversation cannot reference itself"},
        )
    target = await _store.get_conversation(target_id)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "referenced conversation not found"},
        )
    if target.workspace_id != conv.workspace_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_request", "message": "can only reference threads in this workspace"},
        )
    if target.visibility != "shared":
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "only shared conversations can be referenced"},
        )
    await _store.add_reference(
        conversation_id=conversation_id, referenced_conversation_id=target_id
    )
    return {"items": await _reference_summaries(conversation_id)}


@router.delete("/{conversation_id}/references/{referenced_conversation_id}")
async def remove_reference(conversation_id: str, referenced_conversation_id: str):
    """Unlink a referenced conversation (idempotent)."""
    if await _store.get_conversation(conversation_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "conversation not found"},
        )
    await _store.remove_reference(
        conversation_id=conversation_id,
        referenced_conversation_id=referenced_conversation_id,
    )
    return {"items": await _reference_summaries(conversation_id)}


@router.post("/{branch_id}/messages")
async def send_message(branch_id: str, body: SendMessage):
    """Stream one turn as SSE: user_node -> token* -> assistant_node -> [DONE]."""
    branch = await _store.get_branch(branch_id)
    if branch is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "branch not found"},
        )

    references = await _resolve_reference_blocks(branch.conversation_id)
    producer = ChatProducer(get_provider(), references=references)

    async def event_stream():
        async for event in engine.send(
            store=_store,
            producer=producer,
            branch_id=branch_id,
            prompt=body.prompt,
            author_id=body.author_id,
        ):
            yield to_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{branch_id}/messages/from-prompt")
async def send_from_prompt(branch_id: str, body: InsertPrompt):
    """Insert path: run a saved library prompt's body as a chat turn on this branch.

    Proves the library is *reusable* — the same winning prompt can drive a turn in
    any conversation. Streams the same SSE contract as `messages`.
    """
    branch = await _store.get_branch(branch_id)
    if branch is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "branch not found"}
        )
    prompt = await _prompts.get(body.prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "prompt not found"}
        )

    references = await _resolve_reference_blocks(branch.conversation_id)
    producer = ChatProducer(get_provider(), references=references)

    async def event_stream():
        async for event in engine.send(
            store=_store,
            producer=producer,
            branch_id=branch_id,
            prompt=prompt.body,
            author_id=body.author_id,
        ):
            yield to_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{branch_id}/deep")
async def escalate_deep_reasoning(branch_id: str, body: SendMessage):
    """Escalate one turn to Deep Reasoning (Ouroboros), streamed as SSE.

    Same engine, same branch, same event contract as `messages` — only the
    producer differs ("one mount, two producers"). Emits the richer trace:
    user_node -> (step | budget)* -> token (final answer) -> complete ->
    assistant_node -> [DONE].
    """
    if await _store.get_branch(branch_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "branch not found"},
        )
    if not settings.groq_api_key:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "deep_reasoning_unavailable",
                "message": "GROQ_API_KEY is not configured",
            },
        )

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
            author_id=body.author_id,
        ):
            yield to_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
