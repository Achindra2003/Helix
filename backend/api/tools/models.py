"""MCP server registry — the catalog's second source, per workspace.

Two tables rather than one blob of discovered JSON, because the two things
have different lifetimes and different owners. A *server* is configuration a
person entered and expects to persist. A *tool* is something the server said
about itself last time we asked, and it can change under us — which is exactly
the case the `approved_digest` column exists to catch.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import _now


def _uuid() -> str:
    return uuid4().hex


class McpServerRow(Base):
    """One MCP server a workspace has been pointed at."""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    # The owner's label for it ("github"), and the prefix every tool from this
    # server is attributed under in the ledger — `mcp:github`.
    name: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    # Credentials reuse the provider settings' Fernet machinery rather than a
    # second secret store: one encryption seam, one rotation story. Header name
    # and value are separate so a server wanting `X-API-Key` works without a
    # special case for `Authorization`.
    auth_header: Mapped[str] = mapped_column(String, default="")
    auth_value_encrypted: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # The last discovery's outcome, kept so the settings panel can say what
    # went wrong without making the owner re-run it to find out.
    last_error: Mapped[str] = mapped_column(String, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    __table_args__ = (
        # The name is what appears in the ledger and in the allowlist, so two
        # servers sharing one would make a tool call ambiguous after the fact.
        UniqueConstraint("workspace_id", "name", name="uq_mcp_servers_ws_name"),
    )


class McpToolRow(Base):
    """One tool a server advertised, and whether a human has read it.

    `description_digest` is what the server says now; `approved_digest` is what
    an owner actually reviewed. They start equal on first discovery — nothing
    is offered to a model until the owner adds it to the allowlist anyway — and
    a later sync that changes the description leaves them different, which
    marks the tool unavailable until someone looks again.

    That check is the whole defence against a server rewriting what the model
    is told about its own tools after approval. Without it, "the owner approved
    this tool" would mean "the owner approved this tool's *name*".
    """

    __tablename__ = "mcp_tools"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    tool_name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    description_digest: Mapped[str] = mapped_column(String, default="")
    approved_digest: Mapped[str] = mapped_column(String, default="")
    # Remote by definition, so the approval gate is the default. An owner may
    # demote a specific tool — a decision someone took, not one nobody noticed.
    sensitive: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    __table_args__ = (
        UniqueConstraint("server_id", "tool_name", name="uq_mcp_tools_server_name"),
    )
