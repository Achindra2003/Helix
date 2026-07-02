"""The run event contract — the single stream every run emits.

Both producers speak this language; persisting these and fanning them out to
clients is the conversation engine's whole job. SSE and (later) the WebSocket
room serialise these frames. The `kind` field tags each event's type.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class Node:
    """A message as the engine sees it — DB-agnostic.

    The DB-backed store maps its ORM rows to/from this shape, so the engine never
    depends on the database.
    """

    id: str
    branch_id: str
    parent_id: str | None
    seq: int
    role: Literal["user", "assistant", "system"]
    content: str
    author_id: str | None = None
    token_count: int = 0


# --- Core chat events (emitted by every run) ---
@dataclass
class UserNode:
    """The just-persisted user message that opened this run."""

    node: Node
    kind: str = field(default="user_node", init=False)


@dataclass
class Token:
    """One streamed chunk of the assistant's reply."""

    text: str
    kind: str = field(default="token", init=False)


@dataclass
class AssistantNode:
    """The final, persisted assistant message (sent once the stream ends)."""

    node: Node
    kind: str = field(default="assistant_node", init=False)


@dataclass
class Done:
    """End-of-run sentinel."""

    kind: str = field(default="done", init=False)


# --- Deep-reasoning extension events (Ouroboros runs — wired in E3/E4) ---
@dataclass
class DeepRunRegistered:
    """First frame of a *steerable* deep run: the handle for run control.

    The client keeps `run_id` so that when the run pauses (`Waiting`), it can
    POST guidance to `/conversations/deep/runs/{run_id}/steer` and stream the
    continuation.
    """

    run_id: str
    kind: str = field(default="deep_run", init=False)


@dataclass
class Step:
    """One reasoning transition (reason / reflect / synthesize / ...)."""

    idx: int
    node: str
    depth: int
    energy: float
    payload: dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="step", init=False)


@dataclass
class Budget:
    """Token-budget meter update; drives the monitor's budget bar + alert."""

    tokens_used: int
    tokens_budget: int
    pct: float
    kind: str = field(default="budget", init=False)


@dataclass
class Waiting:
    """The run paused, awaiting human input (steer)."""

    reason: str = "steer"
    kind: str = field(default="waiting", init=False)


@dataclass
class Complete:
    """The run finished; carries why it halted and the final status."""

    stop_reason: str
    status: Literal["done", "killed", "error"]
    kind: str = field(default="complete", init=False)


Event = (
    UserNode | Token | AssistantNode | Done
    | DeepRunRegistered | Step | Budget | Waiting | Complete
)


def to_dict(event: Event) -> dict[str, Any]:
    """Serialise an event to a JSON-able dict (the `kind` field tags the type)."""
    return asdict(event)


def to_sse(event: Event) -> str:
    """Render an event as a Server-Sent-Events frame.

    `Done` becomes the conventional `[DONE]` sentinel; everything else is a JSON
    payload carrying its `kind`.
    """
    if isinstance(event, Done):
        return "data: [DONE]\n\n"
    return f"data: {json.dumps(to_dict(event))}\n\n"
