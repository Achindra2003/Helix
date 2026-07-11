from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..errors import api_error
from ..models import Membership, User, Workspace
from ..schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserOut,
)
from ..security import hash_password, make_token, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest, session: AsyncSession = Depends(get_session)
):
    exists = await session.scalar(select(User).where(User.email == body.email))
    if exists:
        raise api_error(409, "conflict", "Email already registered.")

    user = User(email=body.email, pw_hash=hash_password(body.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return AuthResponse(user=UserOut.model_validate(user, from_attributes=True),
                        token=make_token(user.id))


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.pw_hash):
        raise api_error(401, "unauthorized", "Invalid email or password.")

    return AuthResponse(user=UserOut.model_validate(user, from_attributes=True),
                        token=make_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user, from_attributes=True)


@router.patch("/me/password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(body.current_password, user.pw_hash):
        raise api_error(401, "unauthorized", "Current password is incorrect.")
    user.pw_hash = hash_password(body.new_password)
    await session.commit()


@router.delete("/me", status_code=204)
async def delete_account(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Deletes the account, unless the user owns a workspace — a personal
    account deletion must never cascade into wiping a team's shared
    workspace. The owner deletes or (in a future pass) transfers ownership
    of each workspace first; this only ever removes the caller's own rows.

    Authored conversation/document content is left in place (immutable
    history) — `author_id` becomes a dangling reference, which the frontend
    already tolerates elsewhere (falls back to a generic "teammate" label).
    """
    owned = (
        await session.execute(select(Workspace.id, Workspace.name).where(Workspace.owner_id == user.id))
    ).all()
    if owned:
        names = ", ".join(name for _id, name in owned)
        raise api_error(
            409, "owns_workspaces",
            f"Delete or transfer ownership of these workspaces first: {names}.",
        )
    await session.execute(delete(Membership).where(Membership.user_id == user.id))
    await session.delete(user)
    await session.commit()
