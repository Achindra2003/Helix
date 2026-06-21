"""Auth + RBAC dependencies."""
import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .errors import api_error
from .models import ROLE_RANK, Membership, User
from .security import decode_token


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise api_error(401, "unauthorized", "Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    try:
        user_id = decode_token(token)
    except jwt.PyJWTError:
        raise api_error(401, "unauthorized", "Invalid or expired token.")

    user = await session.get(User, user_id)
    if user is None:
        raise api_error(401, "unauthorized", "User no longer exists.")
    return user


async def get_membership(
    workspace_id: str, user: User, session: AsyncSession
) -> Membership:
    """The caller's membership in a workspace, or 403/404."""
    row = await session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user.id,
        )
    )
    if row is None:
        # Don't leak existence of workspaces the caller isn't in.
        raise api_error(404, "not_found", "Workspace not found.")
    return row


def require_role(min_role: str):
    """Dependency factory: caller must have at least `min_role` in {workspace_id}."""
    min_rank = ROLE_RANK[min_role]

    async def checker(
        workspace_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> Membership:
        membership = await get_membership(workspace_id, user, session)
        if ROLE_RANK[membership.role] < min_rank:
            raise api_error(
                403, "forbidden", f"Requires {min_role} role or higher."
            )
        return membership

    return checker
