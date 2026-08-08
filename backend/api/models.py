"""ORM models. M1 scope: users, workspaces, memberships, invites.

Conversations/nodes/branches/prompts/runs (M2-M7) are added as those modules
land. UUID primary keys are stored as strings for SQLite/Postgres portability.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Role names. Owner > Collaborator > Observer (see contract §2).
ROLE_OWNER = "owner"
ROLE_COLLABORATOR = "collaborator"
ROLE_OBSERVER = "observer"
ROLE_RANK = {ROLE_OBSERVER: 0, ROLE_COLLABORATOR: 1, ROLE_OWNER: 2}


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Normalise a datetime to tz-aware UTC. SQLite returns naive datetimes;
    treat those as UTC so comparisons don't raise."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    pw_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceSettings(Base):
    """Per-workspace LLM provider configuration (the BYO-key seam).

    One row per workspace, created lazily on first save. `provider == ""` means
    "inherit the server default" — self-hosters never touch this table. The API
    key is Fernet-encrypted at rest (see `provider_settings.py`) and is
    write-only at the HTTP surface: responses carry a masked form at most.
    """

    __tablename__ = "workspace_settings"

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String, default="")
    api_key_encrypted: Mapped[str] = mapped_column(String, default="")
    base_url: Mapped[str] = mapped_column(String, default="")
    chat_model: Mapped[str] = mapped_column(String, default="")
    deep_model: Mapped[str] = mapped_column(String, default="")
    # Agent tool allowlist (FR-14): a JSON array of tool names, owner-managed.
    # "" = never set = the safe default (workspace-internal tools only);
    # "[]" = the owner explicitly disabled every tool. See api/tools/.
    tool_allowlist: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id", name="uq_member"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    role: Mapped[str] = mapped_column(String, default=ROLE_COLLABORATOR)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    workspace: Mapped["Workspace"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship()


class Invite(Base):
    __tablename__ = "invites"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String, default=ROLE_COLLABORATOR)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Redemption budget (P2). Expiry alone leaves a leaked link usable by
    # everyone who sees it until it lapses; this bounds the blast radius.
    # `uses` counts redemptions that actually created a membership — an
    # existing member re-opening the link is not a use. `max_uses = 0` means
    # unlimited, which is what pre-existing invite rows get from the column
    # shim, so adding this cannot retroactively invalidate live links.
    uses: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)

    @staticmethod
    def default_expiry(days: int = 7) -> datetime:
        return _now() + timedelta(days=days)

    @property
    def is_expired(self) -> bool:
        return as_utc(self.expires_at) < _now()

    @property
    def is_exhausted(self) -> bool:
        return self.max_uses > 0 and self.uses >= self.max_uses

    @property
    def is_usable(self) -> bool:
        return not self.is_expired and not self.is_exhausted


class Notice(Base):
    """Something a teammate needs to know, kept until they have seen it.

    The bell already existed, and it was a session store: a run finishing, a
    thread concluding, all held in the tab's memory. Close the tab and the
    workspace had never told you anything. For a product whose whole claim is
    that the record survives, the one surface that reached a *person* was the
    one surface that forgot.

    It is per-recipient rather than per-event on purpose. Two people mentioned
    in the same note get two rows, because "have you read this" is a fact about
    a person, not about the note — and a shared row would need a join table to
    answer it anyway.

    `excerpt` is denormalised from the node. The node is immutable, so this is
    not a cache that can go stale; it is here so the bell can render without a
    read of every conversation the notice points into.
    """

    __tablename__ = "notices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # Who it is for. Indexed because every read is "my unseen notices".
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    # What kind of thing happened. Today only "mention"; the column exists so
    # the run-finished and thread-concluded events can move off the session
    # store later without a migration.
    kind: Mapped[str] = mapped_column(String, default="mention")
    # Who caused it, and their email — denormalised for the same reason as
    # `excerpt`, and because a removed member's name should still read
    # correctly in a notice they left behind.
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_email: Mapped[str] = mapped_column(String, default="")
    # Where it points. All three are needed to land the reader on the exact
    # turn rather than on the thread's tail.
    conversation_id: Mapped[str] = mapped_column(String, default="", index=True)
    branch_id: Mapped[str] = mapped_column(String, default="")
    node_id: Mapped[str] = mapped_column(String, default="")
    excerpt: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Null until seen. A nullable timestamp rather than a boolean because "when
    # did they see it" is the question that gets asked next.
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
