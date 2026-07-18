"""The tool layer (FR-14 made real): typed tools, a per-workspace allowlist,
and an approval gate for the sensitive ones.

Three policy layers, deliberately separate:
1. **Catalog** — what exists (`builtin.make_tools`). A tool that can't work in
   this deployment (web search without a key) is visibly unavailable, not
   silently missing.
2. **Allowlist** — what this workspace permits (owner-managed, stored on
   `WorkspaceSettings.tool_allowlist`). Only allowed tools are even *offered*
   to the model: an un-allowed tool isn't "refused at call time", it does not
   exist in the model's world — the difference between a locked door and a
   door the model never learns about.
3. **Approval** — sensitive tools (anything that leaves the workspace, e.g.
   web search) additionally pause the run for a human decision before every
   call (`agent.py`'s gate node, a LangGraph interrupt).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class ToolSpec:
    """One callable tool: OpenAI-function-shaped schema + an async handler."""

    name: str
    description: str
    parameters: dict  # JSON schema for the arguments object
    handler: Callable[..., Awaitable[str]]
    sensitive: bool = False  # sensitive ⇒ human approval before every call
    # False = the tool exists but can't work in this deployment (e.g. web
    # search without a key). It stays in the catalog so the settings UI can
    # say *why* it's greyed out, but it is never offered to the model.
    available: bool = True


def openai_schema(spec: ToolSpec) -> dict:
    """The function-calling schema shape every OpenAI-compatible model binds."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


# Safe-by-default: workspace-internal retrieval tools. Web search is opt-in
# (owner adds it to the allowlist) and approval-gated even then.
DEFAULT_ALLOWED = ("search_knowledge_base", "search_conversations")


def resolve_allowlist(raw: str | None) -> list[str]:
    """The workspace's allowed tool names ("" / NULL / invalid = the default).

    An explicit `"[]"` stays empty — an owner who turned every tool off gets
    a tool-less agent, not the default back.
    """
    if not raw:
        return list(DEFAULT_ALLOWED)
    try:
        names = json.loads(raw)
        if isinstance(names, list):
            return [str(n) for n in names]
    except (ValueError, TypeError):
        pass
    return list(DEFAULT_ALLOWED)


def bindable(tools: list[ToolSpec], allowed: list[str]) -> list[ToolSpec]:
    """The tools the model is actually offered: allowed here AND workable in
    this deployment. Everything else stays out of the model's world entirely."""
    return [t for t in tools if t.available and t.name in allowed]
