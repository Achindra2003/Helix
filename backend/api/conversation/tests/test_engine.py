"""Tests for the conversation engine (E2): `send` + `ChatProducer`, against
`InMemoryStore` and stub/fake providers. Proves the orchestration contract —
event order, token relay, and that both the user and assistant turns persist."""
from typing import AsyncIterator

from api.conversation.engine import send
from api.conversation.events import AssistantNode, Complete, Done, Token, UserNode
from api.conversation.producer import ChatProducer
from api.conversation.store import InMemoryStore
from api.providers.stub import StubProvider


async def test_send_persists_through_db_store():
    """E5 integration: the engine + a fake provider running against the real
    DB-backed store, proving the production persistence path end-to-end."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from api.conversation import models  # noqa: F401  (register tables)
    from api.conversation.store import DbStore
    from api.db import Base

    db_engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = DbStore(async_sessionmaker(db_engine, expire_on_commit=False))

    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    producer = ChatProducer(FakeProvider(["Hi", " there"]))
    await _run(store, producer, conv.default_branch_id, "hello")

    history = await store.get_history(conv.default_branch_id)
    assert [(n.role, n.content) for n in history] == [
        ("user", "hello"),
        ("assistant", "Hi there"),
    ]
    await db_engine.dispose()


class FakeProvider:
    """A provider with a fixed, known token stream (no timing, no echo)."""

    name = "fake"

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk

    async def stream_messages(self, messages) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk


async def _branch(store: InMemoryStore) -> str:
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    return conv.default_branch_id


async def _run(store, producer, branch_id, prompt, author_id="u1"):
    return [
        ev async for ev in send(
            store=store,
            producer=producer,
            branch_id=branch_id,
            prompt=prompt,
            author_id=author_id,
        )
    ]


async def test_send_event_order_and_persistence():
    store = InMemoryStore()
    b = await _branch(store)
    producer = ChatProducer(FakeProvider(["Hello", ", ", "world"]))

    events = await _run(store, producer, b, "hi")

    # Order: UserNode, then >=1 Token, then AssistantNode, then Done.
    assert isinstance(events[0], UserNode)
    assert isinstance(events[-1], Done)
    assert isinstance(events[-2], AssistantNode)
    tokens = [e for e in events if isinstance(e, Token)]
    assert [t.text for t in tokens] == ["Hello", ", ", "world"]

    # Assistant reply is the concatenation of the relayed tokens.
    assert events[-2].node.content == "Hello, world"

    # Both turns persisted on the branch, in order.
    history = await store.get_history(b)
    assert [(n.role, n.content) for n in history] == [
        ("user", "hi"),
        ("assistant", "Hello, world"),
    ]
    assert events[0].node.id == history[0].id  # the emitted user node is the stored one


async def test_send_relays_stub_provider_tokens():
    store = InMemoryStore()
    b = await _branch(store)
    producer = ChatProducer(StubProvider())

    events = await _run(store, producer, b, "ping")

    tokens = [e for e in events if isinstance(e, Token)]
    assert tokens, "stub provider should stream at least one token"
    reply = "".join(t.text for t in tokens)
    assert "ping" in reply  # the stub echoes the prompt back


async def test_chat_producer_sees_history_as_messages():
    """Second turn: the producer passes the prior turns as role-structured messages."""
    store = InMemoryStore()
    b = await _branch(store)

    captured: list[list[dict]] = []

    class CapturingProvider:
        name = "capture"

        async def stream_messages(self, messages) -> AsyncIterator[str]:
            captured.append(messages)
            yield "ok"

    producer = ChatProducer(CapturingProvider())
    await _run(store, producer, b, "first")
    await _run(store, producer, b, "second")

    # The second run's messages carry a system frame plus the whole thread so far,
    # as real roles (not a flattened string).
    second = captured[1]
    assert second[0]["role"] == "system"
    roles = [m["role"] for m in second]
    assert roles == ["system", "user", "assistant", "user"]
    contents = " ".join(m["content"] for m in second)
    assert "first" in contents and "second" in contents


async def test_provider_failure_midstream_yields_clean_error_not_crash():
    """P5: a provider that drops mid-stream produces a terminal Complete(error),
    still persists the partial reply, and closes the stream cleanly."""
    store = InMemoryStore()
    b = await _branch(store)

    class FlakyProvider:
        name = "flaky"

        async def stream_messages(self, messages) -> AsyncIterator[str]:
            yield "partial "
            raise RuntimeError("upstream dropped")

    events = await _run(store, ChatProducer(FlakyProvider()), b, "hi")

    errors = [e for e in events if isinstance(e, Complete)]
    assert errors and errors[0].status == "error"
    assert "upstream dropped" in errors[0].stop_reason
    # Stream still closes well-formed, and the partial reply is persisted.
    assert isinstance(events[-1], Done)
    assert isinstance(events[-2], AssistantNode)
    assert events[-2].node.content == "partial "


async def test_empty_prompt_is_handled_gracefully():
    """P5: an empty user turn persists and completes without error."""
    store = InMemoryStore()
    b = await _branch(store)
    events = await _run(store, ChatProducer(FakeProvider(["ok"])), b, "")

    assert isinstance(events[0], UserNode)
    assert isinstance(events[-1], Done)
    history = await store.get_history(b)
    assert history[0].content == ""
