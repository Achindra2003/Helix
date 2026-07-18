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

import time
from typing import AsyncIterator, Awaitable, Callable, Protocol

from ..providers import LLMProvider
from ..telemetry import set_usage_attributes, tracer
from .context import ReferenceBlock, build_messages
from .events import Event, Grounding, Node, Token

# Precomputes the semantic-recall block for a send (persisted-vector path).
Recaller = Callable[[list[Node]], Awaitable[str]]
# Retrieves file-grounding for a send: (rendered block, citation items).
Grounder = Callable[[list[Node]], Awaitable[tuple[str, list[dict]]]]
# Receives (model, usage|None, latency_ms) after each streamed call — the
# accounting seam. The producer stays workspace-ignorant; the router binds it.
UsageSink = Callable[[str, dict | None, int], None]


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
        self,
        provider: LLMProvider,
        references: list[ReferenceBlock] | None = None,
        recaller: Recaller | None = None,
        grounder: Grounder | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        self._provider = provider
        self._references = references
        self._recaller = recaller
        self._grounder = grounder
        self._usage_sink = usage_sink

    async def run(self, history: list[Node]) -> AsyncIterator[Event]:
        # One GenAI span per turn's LLM call. Retrieval below runs before the
        # call and gets its own spans (inside the retrieval modules); the LLM
        # span opens only around the stream so latency means model latency.
        model = getattr(self._provider, "_model", "") or self._provider.name

        # Recall runs against persisted node vectors (and in a worker thread)
        # when a recaller is wired; without one, build_messages falls back to
        # its inline embedding path.
        recalled = await self._recaller(history) if self._recaller else None
        # File grounding: relevant workspace-document chunks, cited to the
        # client before the reply streams so the UI can show its sources.
        grounding_block, citations = (
            await self._grounder(history) if self._grounder else ("", [])
        )
        if citations:
            yield Grounding(items=citations)
        messages = build_messages(
            history,
            references=self._references,
            recalled=recalled,
            grounding=grounding_block or None,
        )

        span = tracer().start_span(
            f"chat {model}",
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.system": self._provider.name,
                "gen_ai.request.model": model,
                "helix.kind": "chat",
                "helix.context_messages": len(messages),
            },
        )
        started = time.monotonic()
        try:
            async for chunk in self._provider.stream_messages(messages):
                yield Token(text=chunk)
        finally:
            # Runs on success, provider error, or an abandoned generator alike —
            # the span and the ledger must never leak open or go unwritten.
            usage = getattr(self._provider, "last_usage", None)
            latency_ms = int((time.monotonic() - started) * 1000)
            set_usage_attributes(span, usage)
            span.end()
            if self._usage_sink is not None:
                self._usage_sink(model, usage, latency_ms)
