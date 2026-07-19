import jwt as pyjwt
from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..email import send as send_email
from ..errors import api_error
from ..models import Membership, User, Workspace
from ..onboarding import seed_example_workspace
from ..schemas import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)
from ..security import (
    decode_reset_token,
    hash_password,
    make_reset_token,
    make_token,
    peek_token_subject,
    verify_password,
)

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

    # After the commit, deliberately: seeding is a nicety and the account is
    # not. seed_example_workspace swallows its own failures for the same
    # reason — a user who cannot register because demo content broke would be
    # a catastrophic trade.
    await seed_example_workspace(session, user.id)

    return AuthResponse(user=UserOut.model_validate(user, from_attributes=True),
                        token=make_token(user.id))


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.pw_hash):
        raise api_error(401, "unauthorized", "Invalid email or password.")

    return AuthResponse(user=UserOut.model_validate(user, from_attributes=True),
                        token=make_token(user.id))


@router.post("/auth/forgot-password", status_code=202)
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(get_session)
):
    """Email a reset link, if that address has an account.

    Always answers 202, whether or not the account exists, and says the same
    thing either way. Anything else turns this endpoint into an account
    enumerator: an attacker submits a list of addresses and learns which ones
    are registered here — worth knowing on its own, and worth more when the
    same people reuse passwords elsewhere.

    For the same reason the response does not depend on whether delivery
    succeeded. Failures are logged server-side (api/email.py).
    """
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is not None:
        token = make_reset_token(user.id, user.pw_hash)
        link = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
        await send_email(
            to=user.email,
            subject="Reset your Helix password",
            text=(
                "Someone asked to reset the password for this Helix account.\n\n"
                f"{link}\n\n"
                f"The link works once and expires in "
                f"{settings.password_reset_ttl_minutes} minutes.\n\n"
                "If this wasn't you, ignore this email — your password has not "
                "changed."
            ),
        )
    return {"status": "accepted"}


@router.post("/auth/reset-password", status_code=204)
async def reset_password(
    body: ResetPasswordRequest, session: AsyncSession = Depends(get_session)
):
    """Set a new password from a reset link.

    The token is verified against the user's *current* password hash, so it
    stops working the moment the reset completes — one link, one use, without a
    table to track spent tokens.
    """
    try:
        user_id = peek_token_subject(body.token)
    except Exception:
        raise api_error(400, "bad_request", "Invalid or expired reset link.")

    user = await session.get(User, user_id)
    if user is None:
        raise api_error(400, "bad_request", "Invalid or expired reset link.")

    try:
        decode_reset_token(body.token, user.pw_hash)
    except pyjwt.PyJWTError:
        # Covers expiry, tampering, a session token presented as a reset token,
        # and a link that has already been used (the hash it was signed against
        # no longer exists). One message for all of them: distinguishing them
        # tells an attacker which guess was closest.
        raise api_error(400, "bad_request", "Invalid or expired reset link.")

    user.pw_hash = hash_password(body.new_password)
    await session.commit()


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
