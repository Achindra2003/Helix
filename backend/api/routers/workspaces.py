import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..conversation.embeddings import EmbeddingIndex, NodeEmbeddingRow
from ..conversation.models import (
    BranchRow,
    ConversationReferenceRow,
    ConversationRow,
    DeepRunRow,
    NodeRow,
)
from ..db import SessionLocal, get_session
from ..deps import get_current_user, get_membership, require_role
from ..documents.models import DocumentChunkRow, DocumentRow
from ..errors import api_error
from ..models import (
    ROLE_COLLABORATOR,
    ROLE_OWNER,
    ROLE_RANK,
    Invite,
    Membership,
    User,
    Workspace,
    WorkspaceSettings,
)
from ..provider_settings import (
    PROVIDER_CHOICES,
    build_chat_provider,
    decrypt_key,
    encrypt_key,
    mask_key,
    resolve,
)
from ..providers.pricing import estimate_cost_usd
from ..telemetry import LlmCallRow
from ..schemas import (
    InviteOut,
    InvitePreview,
    MemberOut,
    RolePatch,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceRename,
)

router = APIRouter(prefix="/api", tags=["workspaces"])

# Cross-conversation semantic search — shares the persisted node_embeddings
# substrate with chat's semantic recall (api/conversation/embeddings.py).
_search_index = EmbeddingIndex(SessionLocal)


def _ws_out(ws: Workspace, role: str) -> WorkspaceOut:
    return WorkspaceOut(
        id=ws.id, name=ws.name, owner_id=ws.owner_id,
        role=role, created_at=ws.created_at,
    )


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Workspace, Membership.role)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user.id)
            .order_by(Workspace.created_at)
        )
    ).all()
    return [_ws_out(ws, role) for ws, role in rows]


@router.post("/workspaces", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    body: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ws = Workspace(name=body.name, owner_id=user.id)
    session.add(ws)
    await session.flush()  # assign ws.id
    session.add(Membership(user_id=user.id, workspace_id=ws.id, role=ROLE_OWNER))
    await session.commit()
    await session.refresh(ws)
    return _ws_out(ws, ROLE_OWNER)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    membership = await get_membership(workspace_id, user, session)
    ws = await session.get(Workspace, workspace_id)
    return _ws_out(ws, membership.role)


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
async def list_members(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_membership(workspace_id, user, session)  # caller must be a member
    rows = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == workspace_id)
            .order_by(Membership.joined_at)
        )
    ).all()
    return [
        MemberOut(user_id=m.user_id, email=u.email, role=m.role, joined_at=m.joined_at)
        for m, u in rows
    ]


@router.patch(
    "/workspaces/{workspace_id}/members/{user_id}", response_model=MemberOut
)
async def update_member_role(
    workspace_id: str,
    user_id: str,
    body: RolePatch,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ROLE_RANK:
        raise api_error(400, "bad_request", f"Unknown role '{body.role}'.")

    target = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )
    if target is None:
        raise api_error(404, "not_found", "Member not found.")

    ws = await session.get(Workspace, workspace_id)
    if user_id == ws.owner_id and body.role != ROLE_OWNER:
        raise api_error(409, "conflict", "Cannot demote the workspace owner.")

    target.role = body.role
    await session.commit()

    u = await session.get(User, user_id)
    return MemberOut(
        user_id=target.user_id, email=u.email,
        role=target.role, joined_at=target.joined_at,
    )


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    workspace_id: str,
    user_id: str,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    """Kick a member (owner-only). The counterpart of voluntary leave — a
    departed or compromised account shouldn't keep tenancy until it chooses
    to go. The canonical owner can't be removed (delete the workspace)."""
    ws = await session.get(Workspace, workspace_id)
    if user_id == ws.owner_id:
        raise api_error(409, "conflict", "Cannot remove the workspace owner.")
    target = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )
    if target is None:
        raise api_error(404, "not_found", "Member not found.")
    await session.delete(target)
    await session.commit()


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def rename_workspace(
    workspace_id: str,
    body: WorkspaceRename,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    ws = await session.get(Workspace, workspace_id)
    ws.name = body.name
    await session.commit()
    await session.refresh(ws)
    return _ws_out(ws, ROLE_OWNER)


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    """Owner-only, cascading. No DB-level FK cascades exist (see api/models.py's
    docstring) — every dependent table is cleared explicitly, in dependency
    order, before the workspace row itself (whose Membership rows the ORM
    relationship cascades via `session.delete`)."""
    ws = await session.get(Workspace, workspace_id)
    conv_ids = select(ConversationRow.id).where(ConversationRow.workspace_id == workspace_id)
    branch_ids = select(BranchRow.id).where(BranchRow.conversation_id.in_(conv_ids))
    node_ids = select(NodeRow.id).where(NodeRow.branch_id.in_(branch_ids))

    await session.execute(delete(NodeEmbeddingRow).where(NodeEmbeddingRow.node_id.in_(node_ids)))
    await session.execute(delete(NodeRow).where(NodeRow.branch_id.in_(branch_ids)))
    await session.execute(delete(BranchRow).where(BranchRow.conversation_id.in_(conv_ids)))
    await session.execute(
        delete(ConversationReferenceRow).where(
            ConversationReferenceRow.conversation_id.in_(conv_ids)
            | ConversationReferenceRow.referenced_conversation_id.in_(conv_ids)
        )
    )
    await session.execute(delete(ConversationRow).where(ConversationRow.workspace_id == workspace_id))
    await session.execute(delete(DeepRunRow).where(DeepRunRow.workspace_id == workspace_id))
    await session.execute(delete(DocumentChunkRow).where(DocumentChunkRow.workspace_id == workspace_id))
    await session.execute(delete(DocumentRow).where(DocumentRow.workspace_id == workspace_id))
    await session.execute(delete(Invite).where(Invite.workspace_id == workspace_id))
    await session.execute(delete(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id))
    await session.delete(ws)  # ORM-cascades this workspace's Membership rows
    await session.commit()


@router.post("/workspaces/{workspace_id}/leave", status_code=204)
async def leave_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Any member may leave except the canonical owner (`Workspace.owner_id`) —
    they delete the workspace instead; transferring ownership is out of scope."""
    membership = await get_membership(workspace_id, user, session)
    ws = await session.get(Workspace, workspace_id)
    if user.id == ws.owner_id:
        raise api_error(
            409, "conflict",
            "The workspace owner can't leave — delete the workspace instead.",
        )
    await session.delete(membership)
    await session.commit()


@router.get("/workspaces/{workspace_id}/usage")
async def get_workspace_usage(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lifetime token usage for this workspace's own BYO key. Chat tokens are
    an approximation — `NodeRow.token_count` is a streamed chunk count, not a
    real tokenizer count (see `api/conversation/engine.py`). Deep-run tokens
    are the real, measured number the engine's usage handler reports."""
    await get_membership(workspace_id, user, session)
    chat_tokens = await session.scalar(
        select(func.coalesce(func.sum(NodeRow.token_count), 0))
        .select_from(NodeRow)
        .join(BranchRow, BranchRow.id == NodeRow.branch_id)
        .join(ConversationRow, ConversationRow.id == BranchRow.conversation_id)
        .where(ConversationRow.workspace_id == workspace_id, NodeRow.role == "assistant")
    )
    deep_tokens = await session.scalar(
        select(func.coalesce(func.sum(DeepRunRow.tokens_used), 0))
        .where(DeepRunRow.workspace_id == workspace_id)
    )

    # The ledger: one row per LLM call with provider-reported usage — the
    # real numbers, aggregated per (kind, model) so pricing can apply.
    grouped = (
        await session.execute(
            select(
                LlmCallRow.kind,
                LlmCallRow.provider,
                LlmCallRow.model,
                func.count(LlmCallRow.id),
                func.coalesce(func.sum(LlmCallRow.input_tokens), 0),
                func.coalesce(func.sum(LlmCallRow.output_tokens), 0),
            )
            .where(LlmCallRow.workspace_id == workspace_id)
            .group_by(LlmCallRow.kind, LlmCallRow.provider, LlmCallRow.model)
        )
    ).all()
    calls = []
    total_cost: float | None = None
    for kind, provider, model, count, in_tok, out_tok in grouped:
        cost = estimate_cost_usd(model, int(in_tok), int(out_tok))
        if cost is not None:
            total_cost = (total_cost or 0.0) + cost
        calls.append(
            {
                "kind": kind,
                "provider": provider,
                "model": model,
                "calls": int(count),
                "input_tokens": int(in_tok),
                "output_tokens": int(out_tok),
                "cost_usd": round(cost, 6) if cost is not None else None,
            }
        )
    return {
        "chat_tokens_approx": int(chat_tokens or 0),
        "deep_run_tokens": int(deep_tokens or 0),
        # Provider-reported usage per (kind, model); cost is an estimate from
        # a static price table (None when the model isn't listed).
        "calls": calls,
        "estimated_cost_usd": round(total_cost, 6) if total_cost is not None else None,
    }


class SearchQuery(BaseModel):
    query: str
    k: int = 10


@router.post("/workspaces/{workspace_id}/search")
async def search_workspace(
    workspace_id: str,
    body: SearchQuery,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Semantic search across the workspace's conversation history — any
    member's shared threads, plus the caller's own private ones."""
    await get_membership(workspace_id, user, session)
    items = await _search_index.search_workspace(
        workspace_id, user.id, body.query, k=body.k
    )
    return {"items": items}


# --- Provider settings (BYO key) ---
class ProviderSettingsIn(BaseModel):
    provider: str = ""  # "" = inherit the server default
    # None = keep the stored key; "" = clear it; anything else = replace it.
    api_key: str | None = None
    base_url: str = ""
    chat_model: str = ""
    deep_model: str = ""


def _provider_out(row: WorkspaceSettings | None, *, owner: bool) -> dict:
    resolved = resolve(row)
    out = {
        "provider": row.provider if row else "",
        "chat_model": row.chat_model if row else "",
        "deep_model": row.deep_model if row else "",
        # What calls will actually use after fallback — the UI's source of truth
        # for "is the composer alive?" and "which model answers here?".
        "effective_provider": resolved.provider,
        "effective_chat_model": resolved.chat_model,
        "effective_deep_model": resolved.resolved_deep_model,
        "source": resolved.source,
        "configured": not resolved.missing_key,
        "deep_available": bool(resolved.deep_groq_key),
    }
    if owner:
        # Key material stays owner-only, and even then only in masked form.
        out["base_url"] = row.base_url if row else ""
        out["api_key_masked"] = mask_key(decrypt_key(row.api_key_encrypted)) if row else ""
    return out


@router.get("/workspaces/{workspace_id}/settings/provider")
async def get_provider_settings(
    workspace_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Any member may read (the composer needs `configured`); key material and
    base URL are included for owners only."""
    membership = await get_membership(workspace_id, user, session)
    row = await session.get(WorkspaceSettings, workspace_id)
    return _provider_out(row, owner=membership.role == ROLE_OWNER)


@router.put("/workspaces/{workspace_id}/settings/provider")
async def put_provider_settings(
    workspace_id: str,
    body: ProviderSettingsIn,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    provider = body.provider.lower().strip()
    if provider not in PROVIDER_CHOICES:
        raise api_error(
            400, "bad_request", f"Unknown provider '{provider}'. One of: {PROVIDER_CHOICES}."
        )
    base_url = body.base_url.strip().rstrip("/")
    if provider == "openai_compatible":
        if not base_url.startswith(("http://", "https://")):
            raise api_error(
                400, "bad_request", "openai_compatible needs a base_url starting http(s)://."
            )
    row = await session.get(WorkspaceSettings, workspace_id)
    if row is None:
        row = WorkspaceSettings(workspace_id=workspace_id)
        session.add(row)
    row.provider = provider
    row.base_url = base_url
    row.chat_model = body.chat_model.strip()
    row.deep_model = body.deep_model.strip()
    if body.api_key is not None:  # None = keep; "" = clear; else replace
        row.api_key_encrypted = encrypt_key(body.api_key.strip())
    await session.commit()
    await session.refresh(row)
    return _provider_out(row, owner=True)


@router.post("/workspaces/{workspace_id}/settings/provider/test")
async def test_provider_settings(
    workspace_id: str,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    """One cheap live round-trip through the *stored* settings (save, then test).

    Returns ``{ok, detail}`` rather than an HTTP error for provider failures —
    a bad key is a result, not an exception.
    """
    row = await session.get(WorkspaceSettings, workspace_id)
    resolved = resolve(row)
    if resolved.missing_key:
        return {"ok": False, "detail": "No API key configured for this provider."}
    # Bare provider: the owner wants the real, immediate error, not retried or
    # masked by a server fallback.
    provider = build_chat_provider(resolved, resilient=False)
    try:
        first = ""
        async for chunk in provider.stream_messages(
            [{"role": "user", "content": "Reply with the single word: ok"}]
        ):
            first += chunk
            if len(first) >= 40:
                break
        if "rate limit" in first.lower():
            return {"ok": False, "detail": first.strip()[:200]}
        return {"ok": True, "detail": f"{resolved.provider} answered: {first.strip()[:80]}"}
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}


# --- Invites (§5) ---
class InviteCreate(BaseModel):
    role: str = ROLE_COLLABORATOR  # collaborator | observer


@router.post("/workspaces/{workspace_id}/invites", response_model=InviteOut, status_code=201)
async def create_invite(
    workspace_id: str,
    body: InviteCreate | None = None,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    # The invite carries the role the joiner will get. Owner can't be granted by
    # link — ownership is transferred explicitly, never mass-mailed.
    role = (body.role if body else ROLE_COLLABORATOR) or ROLE_COLLABORATOR
    if role not in ROLE_RANK or role == ROLE_OWNER:
        raise api_error(400, "bad_request", f"Invites cannot grant role '{role}'.")
    token = secrets.token_urlsafe(24)
    invite = Invite(
        token=token,
        workspace_id=workspace_id,
        created_by=_owner.user_id,
        role=role,
        expires_at=Invite.default_expiry(),
    )
    session.add(invite)
    await session.commit()
    return InviteOut(
        token=token,
        url=f"{settings.frontend_base_url}/invite/{token}",
        expires_at=invite.expires_at,
    )


@router.get("/workspaces/{workspace_id}/invites")
async def list_invites(
    workspace_id: str,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    """Outstanding (unexpired) invites — so a leaked link is visible, not a
    mystery. Owner-only: tokens are the secret itself."""
    rows = (
        await session.execute(
            select(Invite)
            .where(Invite.workspace_id == workspace_id)
            .order_by(Invite.created_at.desc())
        )
    ).scalars().all()
    return {
        "items": [
            {
                "token": inv.token,
                "role": inv.role,
                "created_at": inv.created_at,
                "expires_at": inv.expires_at,
                "url": f"{settings.frontend_base_url}/invite/{inv.token}",
            }
            for inv in rows
            if not inv.is_expired
        ]
    }


@router.delete("/workspaces/{workspace_id}/invites/{token}", status_code=204)
async def revoke_invite(
    workspace_id: str,
    token: str,
    _owner: Membership = Depends(require_role(ROLE_OWNER)),
    session: AsyncSession = Depends(get_session),
):
    """Revoke an invite before its expiry — the answer to a leaked link."""
    inv = await session.get(Invite, token)
    if inv is None or inv.workspace_id != workspace_id:
        raise api_error(404, "not_found", "Invite not found.")
    await session.delete(inv)
    await session.commit()


@router.get("/invites/{token}", response_model=InvitePreview)
async def preview_invite(token: str, session: AsyncSession = Depends(get_session)):
    invite = await session.get(Invite, token)
    if invite is None or invite.is_expired:
        raise api_error(404, "not_found", "Invite is invalid or expired.")
    ws = await session.get(Workspace, invite.workspace_id)
    return InvitePreview(workspace_name=ws.name)


@router.post("/invites/{token}/accept", response_model=WorkspaceOut)
async def accept_invite(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    invite = await session.get(Invite, token)
    if invite is None or invite.is_expired:
        raise api_error(404, "not_found", "Invite is invalid or expired.")

    existing = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == invite.workspace_id,
            Membership.user_id == user.id,
        )
    )
    if existing is None:
        session.add(
            Membership(
                user_id=user.id,
                workspace_id=invite.workspace_id,
                role=invite.role,
            )
        )
        await session.commit()
        role = invite.role
    else:
        role = existing.role

    ws = await session.get(Workspace, invite.workspace_id)
    return _ws_out(ws, role)
