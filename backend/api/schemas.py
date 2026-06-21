"""Pydantic request/response models — the wire shapes from the API contract."""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Auth (§4) ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)


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


# --- Workspaces (§5) ---
class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceOut(BaseModel):
    id: str
    name: str
    owner_id: str
    role: str  # the caller's role in this workspace
    created_at: datetime


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
