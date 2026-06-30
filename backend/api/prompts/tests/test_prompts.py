"""Tests for the shared prompt library (F4) — save/get/search and the reuse path.

The headline proof (`test_winning_prompt_reused_across_conversations`) shows the
product claim: a saved "winning" prompt drives a turn in two *different*
conversations, each carrying the same prompt body — that's the library being an
asset the whole team reuses.
"""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.conversation.engine import send
from api.conversation.producer import ChatProducer
from api.conversation.store import DbStore
from api.prompts.store import PromptStore
from api.providers.stub import StubProvider


@pytest.fixture
async def session_factory():
    from api.conversation import models  # noqa: F401  (register tables)
    from api.prompts import models as prompt_models  # noqa: F401
    from api.db import Base

    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_save_and_get_roundtrip(session_factory):
    store = PromptStore(session_factory)
    saved = await store.save(
        workspace_id="w1", author_id="alice", title="Summarize",
        body="Summarize the thread in 3 bullets.", tags=["Summary", "summary", " QA "],
    )
    fetched = await store.get(saved.id)
    assert fetched is not None
    assert fetched.body == "Summarize the thread in 3 bullets."
    assert fetched.tags == ["summary", "qa"]  # normalized + de-duped


async def test_get_missing_returns_none(session_factory):
    assert await PromptStore(session_factory).get("nope") is None


async def test_list_is_workspace_scoped(session_factory):
    store = PromptStore(session_factory)
    await store.save(workspace_id="w1", author_id="a", title="A", body="a")
    await store.save(workspace_id="w2", author_id="b", title="B", body="b")
    w1 = await store.list("w1")
    assert [p.title for p in w1] == ["A"]


async def test_search_by_text_and_tag(session_factory):
    store = PromptStore(session_factory)
    await store.save(workspace_id="w1", author_id="a", title="Bug triage", body="Find the root cause", tags=["debug"])
    await store.save(workspace_id="w1", author_id="a", title="Release notes", body="Draft changelog", tags=["writing"])

    assert {p.title for p in await store.list("w1", query="root cause")} == {"Bug triage"}
    assert {p.title for p in await store.list("w1", query="DRAFT")} == {"Release notes"}
    assert {p.title for p in await store.list("w1", tag="debug")} == {"Bug triage"}
    assert await store.list("w1", tag="missing") == []


async def test_winning_prompt_reused_across_conversations(session_factory):
    """The reuse/insert path: one saved prompt drives a turn in two conversations."""
    prompts = PromptStore(session_factory)
    convs = DbStore(session_factory)
    producer = ChatProducer(StubProvider())

    winning = await prompts.save(
        workspace_id="w1", author_id="alice", title="Root-cause",
        body="List the three most likely root causes.", tags=["debug"],
    )

    for _ in range(2):
        conv = await convs.create_conversation(
            workspace_id="w1", author_id="bob", title="incident", visibility="shared"
        )
        # Insert path: the saved prompt body becomes the user turn.
        fetched = await prompts.get(winning.id)
        async for _ev in send(
            store=convs, producer=producer,
            branch_id=conv.default_branch_id, prompt=fetched.body, author_id="bob",
        ):
            pass

        history = await convs.get_history(conv.default_branch_id)
        assert history[0].role == "user"
        assert history[0].content == "List the three most likely root causes."
