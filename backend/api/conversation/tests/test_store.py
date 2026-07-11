"""Tests for the conversation store — especially the fork read path (A1), which
the design flags as where bugs hide. Each test runs against BOTH the in-memory
store and the DB-backed store (parametrized), so the durable store is held to the
exact same contract — that equivalence is what makes the production swap safe.
"""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.conversation.store import ConversationStore, DbStore, InMemoryStore


@pytest.fixture(params=["memory", "db"])
async def store(request):
    if request.param == "memory":
        yield InMemoryStore()
        return
    # Shared-cache in-memory SQLite (StaticPool keeps the one connection alive so
    # every session sees the same database). Importing the models registers them.
    from api.conversation import models  # noqa: F401
    from api.db import Base

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield DbStore(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


async def _conv(store):
    return await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )


async def test_create_conversation_makes_empty_root_branch(store):
    conv = await _conv(store)
    branch = await store.get_branch(conv.default_branch_id)
    assert branch is not None
    assert branch.name == "main"
    assert branch.parent_branch_id is None
    assert branch.head_node_id is None
    assert await store.get_history(branch.id) == []


async def test_add_node_sequences_and_chains_parent(store):
    conv = await _conv(store)
    b = conv.default_branch_id
    n1 = await store.add_node(branch_id=b, role="user", content="hi", author_id="u1")
    n2 = await store.add_node(branch_id=b, role="assistant", content="hello", author_id=None)
    assert (n1.seq, n2.seq) == (0, 1)
    assert n1.parent_id is None
    assert n2.parent_id == n1.id
    branch = await store.get_branch(b)
    assert branch.head_node_id == n2.id
    assert [n.content for n in await store.get_history(b)] == ["hi", "hello"]


async def test_fork_is_o1_and_history_crosses_branch_boundary(store):
    conv = await _conv(store)
    b = conv.default_branch_id
    n1 = await store.add_node(branch_id=b, role="user", content="A", author_id="u1")
    await store.add_node(branch_id=b, role="assistant", content="B", author_id=None)

    # Fork at n1 (before "B"): one new branch row, no history copied.
    fork = await store.create_branch(conversation_id=conv.id, from_node_id=n1.id, name="alt")
    assert fork.fork_node_id == n1.id
    assert fork.head_node_id == n1.id

    # The fork's history is the parent's spine up to the fork point.
    assert [n.content for n in await store.get_history(fork.id)] == ["A"]

    # Continue the fork independently; it chains off the fork node, not "B".
    n3 = await store.add_node(branch_id=fork.id, role="assistant", content="C", author_id=None)
    assert n3.parent_id == n1.id
    assert [n.content for n in await store.get_history(fork.id)] == ["A", "C"]

    # The original branch is untouched.
    assert [n.content for n in await store.get_history(b)] == ["A", "B"]


async def test_store_satisfies_the_protocol(store):
    assert isinstance(store, ConversationStore)


async def test_delete_last_turn_removes_reply_and_user_message(store):
    conv = await _conv(store)
    b = conv.default_branch_id
    n1 = await store.add_node(branch_id=b, role="user", content="A", author_id="u1")
    n2 = await store.add_node(branch_id=b, role="assistant", content="B", author_id=None)

    removed = await store.delete_last_turn(branch_id=b, user_id="u1")
    assert set(removed) == {n1.id, n2.id}
    assert await store.get_history(b) == []
    branch = await store.get_branch(b)
    assert branch.head_node_id is None


async def test_delete_last_turn_removes_only_the_dangling_user_message(store):
    """A user turn with no reply yet (e.g. the send failed) — delete just it."""
    conv = await _conv(store)
    b = conv.default_branch_id
    n1 = await store.add_node(branch_id=b, role="user", content="A", author_id="u1")

    removed = await store.delete_last_turn(branch_id=b, user_id="u1")
    assert removed == [n1.id]
    assert await store.get_history(b) == []


async def test_delete_last_turn_rejects_a_non_author(store):
    conv = await _conv(store)
    b = conv.default_branch_id
    await store.add_node(branch_id=b, role="user", content="A", author_id="u1")
    await store.add_node(branch_id=b, role="assistant", content="B", author_id=None)

    with pytest.raises(PermissionError):
        await store.delete_last_turn(branch_id=b, user_id="someone-else")


async def test_delete_last_turn_rejects_an_empty_branch(store):
    conv = await _conv(store)
    with pytest.raises(KeyError):
        await store.delete_last_turn(branch_id=conv.default_branch_id, user_id="u1")


async def test_delete_last_turn_blocked_once_something_has_forked_from_it(store):
    conv = await _conv(store)
    b = conv.default_branch_id
    n1 = await store.add_node(branch_id=b, role="user", content="A", author_id="u1")
    n2 = await store.add_node(branch_id=b, role="assistant", content="B", author_id=None)
    await store.create_branch(conversation_id=conv.id, from_node_id=n2.id, name="alt")

    with pytest.raises(ValueError):
        await store.delete_last_turn(branch_id=b, user_id="u1")

    # Untouched — the fork's history is still intact.
    assert [n.content for n in await store.get_history(b)] == ["A", "B"]

    # A fork from an earlier ancestor also blocks deleting that ancestor even
    # after the trailing turn (the direct fork target) is gone — but the
    # trailing turn itself, once safely removed, doesn't block on ancestors.
    n3 = await store.add_node(branch_id=b, role="user", content="C", author_id="u1")
    n4 = await store.add_node(branch_id=b, role="assistant", content="D", author_id=None)
    removed = await store.delete_last_turn(branch_id=b, user_id="u1")
    assert set(removed) == {n3.id, n4.id}
