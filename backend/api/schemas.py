"""Pydantic request/response models — the wire shapes from the API contract."""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Auth (§4) ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)
    # Only consulted when the instance is invite-only (settings.allow_registration
    # is False), where it is what admits the caller. Never redeemed here — the
    # client accepts the invite after signing in, so there is exactly one code
    # path that spends a use.
    invite: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime | None = None


class AuthResponse(BaseModel):
    user: UserOut
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=200)



class DeleteAccountRequest(BaseModel):
    """Deleting an account is irreversible, so it re-authenticates.

    Changing a password already required the current one; deleting the whole
    account required nothing but a bearer token, and tokens last a week — the
    weaker gate was on the more destructive action, so a borrowed token or an
    unlocked laptop was enough.
    """

    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    # Same floor as registration: a reset must not be a way around the policy.
    new_password: str = Field(min_length=6, max_length=200)


# --- Workspaces (§5) ---
class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceOut(BaseModel):
    id: str
    name: str
    owner_id: str
    role: str  # the caller's role in this workspace
    created_at: datetime
    # What is inside, so a picker card can say something about the workspace
    # beyond its name. Populated by the list endpoint only; a workspace just
    # created has one member and no threads, which is what the defaults say.
    #
    # `conversation_count` is what *this caller* may open — shared threads plus
    # their own private ones. Counting another member's private threads would
    # advertise their existence on a card, which is the one thing private
    # visibility promises it will not do.
    conversation_count: int = 0
    member_count: int = 1


class MemberOut(BaseModel):
    user_id: str
    email: str
    role: str
    joined_at: datetime


class RolePatch(BaseModel):
    role: str  # owner | collaborator | observer


# --- Invites (§5) ---
class InviteOut(BaseModel):
    token: str
    url: str
    expires_at: datetime


class InvitePreview(BaseModel):
    workspace_name: str
