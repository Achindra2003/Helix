"""The conversation engine — `send()`.

This is "the AI portion" the project is built around: prompt -> provider stream
-> persist as nodes. It is producer-agnostic and store-agnostic; it depends only
on the `ConversationStore` and `Producer` seams, so it is exercised end-to-end by
tests using `InMemoryStore` + the stub provider, and runs unchanged against the
DB-backed store and the deep-reasoning producer later.

One run does exactly this:
  1. persist the user message as a node      -> emit `UserNode`
  2. run the producer over the branch history -> relay its events, accumulating
     `Token` text into the assistant reply
  3. persist the assistant message as a node  -> emit `AssistantNode`
  4. emit `Done`

Robustness: if a producer raises mid-stream (e.g. the provider drops), the engine
catches it, emits a clean terminal `Complete(status="error")` event, and still
persists whatever partial reply arrived + closes with `AssistantNode`/`Done` — so
a client sees a well-formed stream, never a torn connection or a 500.
"""
from __future__ import annotations

from typing import AsyncIterator

from .events import AssistantNode, Complete, Done, Event, Token, UserNode, Waiting
from .producer import Producer
from .store import ConversationStore


async def send(
    *,
    store: ConversationStore,
    producer: Producer,
    branch_id: str,
    prompt: str,
    author_id: str,
) -> AsyncIterator[Event]:
    """Run one turn on `branch_id`, yielding the full event stream in order."""
    user_node = await store.add_node(
        branch_id=branch_id, role="user", content=prompt, author_id=author_id
    )
    yield UserNode(node=user_node)

    history = await store.get_history(branch_id)

    parts: list[str] = []
    try:
        async for event in producer.run(history):
            if isinstance(event, Token):
                parts.append(event.text)
            yield event
    except Exception as exc:  # provider/engine failure -> clean terminal event
        yield Complete(stop_reason=f"error: {exc}", status="error")

    assistant_node = await store.add_node(
        branch_id=branch_id,
        role="assistant",
        content="".join(parts),
        author_id=None,
        token_count=len(parts),
    )
    yield AssistantNode(node=assistant_node)

    yield Done()


class ResumableRun:
    """A deep-reasoning turn that can pause at a human steer checkpoint (FR-11).

    Same contract as `send()`, split at the pause: `start()` persists the user
    node and streams until the producer either finishes or pauses at a steer
    interrupt (a `Waiting` event ends the stream). While paused, `steer()`
    resumes from the engine's checkpoint — injecting the human guidance — and
    streams the continuation; a run may pause any number of times. The
    assistant node is persisted only when the run truly completes, so a paused
    run never leaves an empty reply on the branch. Token text accumulates
    across all segments into that one final reply.
    """

    def __init__(self, *, store: ConversationStore, producer, branch_id: str) -> None:
        self._store = store
        self._producer = producer
        self._branch_id = branch_id
        self._parts: list[str] = []
        self.paused = False

    async def start(self, *, prompt: str, author_id: str) -> AsyncIterator[Event]:
        user_node = await self._store.add_node(
            branch_id=self._branch_id, role="user", content=prompt, author_id=author_id
        )
        yield UserNode(node=user_node)
        history = await self._store.get_history(self._branch_id)
        async for event in self._drive(self._producer.run(history)):
            yield event

    async def steer(self, guidance: str) -> AsyncIterator[Event]:
        """Resume a paused run with (possibly empty) human guidance."""
        self.paused = False
        async for event in self._drive(self._producer.resume(guidance)):
            yield event

    async def _drive(self, gen) -> AsyncIterator[Event]:
        try:
            async for event in gen:
                if isinstance(event, Token):
                    self._parts.append(event.text)
                if isinstance(event, Waiting):
                    self.paused = True
                yield event
        except Exception as exc:  # mirror send(): clean terminal event
            yield Complete(stop_reason=f"error: {exc}", status="error")

        if self.paused:
            return  # mid-run; the reply isn't finished, persist nothing yet

        assistant_node = await self._store.add_node(
            branch_id=self._branch_id,
            role="assistant",
            content="".join(self._parts),
            author_id=None,
            token_count=len(self._parts),
        )
        yield AssistantNode(node=assistant_node)
        yield Done()
