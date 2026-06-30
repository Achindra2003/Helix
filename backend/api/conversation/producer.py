"""Producers — the swappable "brain" of a run.

A producer takes the conversation history and emits the *content* events of a
run. There are two (architecture: "one mount, two producers"):

- `ChatProducer` (here, E2) wraps the streaming `LLMProvider` and emits `Token`s.
- `DeepReasoningProducer` (E3, Ouroboros) maps the engine's `astream` events to
  `Step` / `Budget` / `Token` / `Waiting` / `Complete`.

Both speak the same event contract; `engine.send` brackets whatever a producer
emits with the persistence events (`UserNode`, `AssistantNode`, `Done`), so the
orchestrator never needs to know which producer is running.
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol

from ..providers import LLMProvider
from .context import ReferenceBlock, build_messages
from .events import Event, Node, Token


class Producer(Protocol):
    """Emits the content events of a run, given the history (root -> head).

    The last node in `history` is the user message that opened the run.
    """

    def run(self, history: list[Node]) -> AsyncIterator[Event]: ...


class ChatProducer:
    """The everyday-chat producer: one streamed provider call, relayed as tokens.

    History is rendered to role-structured chat messages (`context.build_messages`),
    so the model receives the thread's *shared, branchable context* as real
    `system`/`user`/`assistant` turns — including, on a forked branch, exactly the
    inherited ancestor spine and nothing from sibling branches.

    `references` are other conversations the user has linked in: their current
    context is folded into the system frame so a reply can draw on another thread
    without those messages joining this branch's own lineage.
    """

    def __init__(
        self, provider: LLMProvider, references: list[ReferenceBlock] | None = None
    ) -> None:
        self._provider = provider
        self._references = references

    async def run(self, history: list[Node]) -> AsyncIterator[Event]:
        messages = build_messages(history, references=self._references)
        async for chunk in self._provider.stream_messages(messages):
            yield Token(text=chunk)
