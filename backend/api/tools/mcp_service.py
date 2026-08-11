"""Reading the MCP registry into the tool catalog, and refreshing it.

Kept apart from `mcp.py` (which speaks the protocol) and from the router
(which speaks HTTP), because the interesting logic is neither: it is the rule
about *what counts as approved*, and that rule wants to be readable on its own.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from ..provider_settings import decrypt_key
from . import ToolSpec
from .mcp import McpClient, McpError, describe_digest, make_mcp_tools
from .models import McpServerRow, McpToolRow


@dataclass
class ServerView:
    """A server with its credential decrypted, ready to call.

    A separate object from the row on purpose: the plaintext secret exists for
    the lifetime of one request and never sits on an ORM instance that might be
    serialised into a response by accident.
    """

    name: str
    url: str
    auth_header: str
    auth_value: str
    enabled: bool


async def load_mcp_tools(session, workspace_id: str) -> list[ToolSpec]:
    """Every MCP tool this workspace has, as catalog entries.

    Never raises. A misconfigured or unreachable server must not be able to
    stop an agent run from starting — the tools it would have contributed are
    simply absent, exactly as an unavailable built-in is.
    """
    try:
        servers = (
            await session.execute(
                select(McpServerRow).where(McpServerRow.workspace_id == workspace_id)
            )
        ).scalars().all()
        if not servers:
            return []
        rows = (
            await session.execute(
                select(McpToolRow).where(McpToolRow.workspace_id == workspace_id)
            )
        ).scalars().all()
    except Exception:
        return []

    by_server: dict[str, list[McpToolRow]] = {}
    for row in rows:
        by_server.setdefault(row.server_id, []).append(row)

    specs: list[ToolSpec] = []
    for server in servers:
        view = ServerView(
            name=server.name,
            url=server.url,
            auth_header=server.auth_header,
            auth_value=decrypt_key(server.auth_value_encrypted),
            enabled=server.enabled,
        )
        specs.extend(make_mcp_tools(server=view, tools=by_server.get(server.id, [])))
    return specs


async def sync_server(session, server: McpServerRow) -> dict:
    """Ask a server what it offers, and reconcile with what we already knew.

    Three cases, and the middle one is the whole point:

    - **New tool** — stored, with `approved_digest` equal to what was
      discovered. That is not an approval: nothing is offered to a model until
      the owner adds the name to the allowlist. It means "this is the version a
      human will be shown".
    - **Changed description or schema** — `description_digest` moves and
      `approved_digest` does not, which makes the tool unavailable until
      someone re-reviews it. A server that can silently rewrite what the model
      is told about its own tools would make the allowlist meaningless.
    - **Gone** — the row is deleted. A tool the server no longer offers should
      not linger in a settings panel implying it could be turned on.
    """
    view = ServerView(
        name=server.name,
        url=server.url,
        auth_header=server.auth_header,
        auth_value=decrypt_key(server.auth_value_encrypted),
        enabled=server.enabled,
    )
    client = McpClient(
        url=view.url,
        auth_header=view.auth_header,
        auth_value=view.auth_value,
        name=view.name,
    )
    try:
        discovered = await client.list_tools()
    except McpError as exc:
        server.last_error = str(exc)[:400]
        await session.commit()
        raise
    except Exception as exc:  # noqa: BLE001 — a foreign server, any failure
        server.last_error = f"{type(exc).__name__}: {exc}"[:400]
        await session.commit()
        raise McpError(server.last_error) from exc

    existing = {
        row.tool_name: row
        for row in (
            await session.execute(
                select(McpToolRow).where(McpToolRow.server_id == server.id)
            )
        ).scalars()
    }
    seen: set[str] = set()
    added, changed = 0, 0

    for tool in discovered:
        seen.add(tool["name"])
        digest = describe_digest(tool["description"], tool["input_schema"])
        row = existing.get(tool["name"])
        if row is None:
            session.add(
                McpToolRow(
                    server_id=server.id,
                    workspace_id=server.workspace_id,
                    tool_name=tool["name"],
                    description=tool["description"],
                    input_schema=json.dumps(tool["input_schema"]),
                    description_digest=digest,
                    approved_digest=digest,
                    sensitive=True,  # remote by definition
                )
            )
            added += 1
            continue
        if row.description_digest != digest:
            changed += 1
        row.description = tool["description"]
        row.input_schema = json.dumps(tool["input_schema"])
        row.description_digest = digest

    for name, row in existing.items():
        if name not in seen:
            await session.delete(row)

    server.last_error = ""
    server.last_synced_at = datetime.now(timezone.utc)
    await session.commit()
    return {
        "discovered": len(discovered),
        "added": added,
        # Tools whose description moved under an owner who had already reviewed
        # them. Surfaced in the response because it is the one number worth
        # interrupting someone about.
        "needs_review": changed,
        "removed": len(set(existing) - seen),
    }
