"""Citations survive the tab.

The defect these cover: a grounded reply announced its sources on the event
stream, the browser held them in memory, and a reload dropped them. The reply
persisted; the evidence for it did not. Everything here is about the sources
outliving the request that produced them — through the store, through a
reload, through a fork, and into both exports.
"""
from typing import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.conversation import models  # noqa: F401  (register tables)
from api.conversation.engine import send
from api.conversation.events import AssistantNode
from api.conversation.producer import ChatProducer
from api.conversation.store import DbStore, InMemoryStore
from api.db import Base

CITES = [
    {
        "document_id": "d1",
        "filename": "spec.pdf",
        "chunk_index": 2,
        "score": 0.81,
        "excerpt": "the retrieval floor is calibrated on the golden set",
    },
    {
        "document_id": "d2",
        "filename": "runbook.md",
        "chunk_index": 0,
        "score": 0.66,
        "excerpt": "restart the worker before draining the queue",
    },
]


class FakeProvider:
    name = "fake"

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def stream_messages(self, messages) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk


def _grounder(items):
    async def ground(history):
        return ("[sources]", list(items))

    return ground


async def _db_store():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return DbStore(async_sessionmaker(engine, expire_on_commit=False)), engine


async def _run(store, branch_id, prompt="what does the spec say?", items=CITES):
    producer = ChatProducer(FakeProvider(["An ", "answer"]), grounder=_grounder(items))
    return [
        ev
        async for ev in send(
            store=store,
            producer=producer,
            branch_id=branch_id,
            prompt=prompt,
            author_id="u1",
        )
    ]


@pytest.mark.parametrize("make_store", ["memory", "db"])
async def test_citations_land_on_the_assistant_node(make_store):
    """Both stores satisfy the same contract — that is what the Protocol is for."""
    engine = None
    if make_store == "memory":
        store = InMemoryStore()
    else:
        store, engine = await _db_store()

    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    events = await _run(store, conv.default_branch_id)

    node = [e for e in events if isinstance(e, AssistantNode)][-1].node
    assert [c["filename"] for c in node.citations] == ["spec.pdf", "runbook.md"]

    if engine is not None:
        await engine.dispose()


async def test_citations_survive_a_reload():
    """The actual bug. A fresh read of the branch — the reload path — must
    return the sources, because nothing about the browser's memory is involved."""
    store, engine = await _db_store()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    await _run(store, conv.default_branch_id)

    history = await store.get_history(conv.default_branch_id)
    user, assistant = history

    assert user.citations == [], "a question has no sources"
    assert [c["document_id"] for c in assistant.citations] == ["d1", "d2"]
    assert assistant.citations[0]["chunk_index"] == 2
    assert assistant.citations[0]["score"] == pytest.approx(0.81)
    assert "golden set" in assistant.citations[0]["excerpt"]
    await engine.dispose()


async def test_citation_order_is_relevance_order():
    """Chips render in the order the retriever ranked them, not row order."""
    store, engine = await _db_store()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    items = [dict(c, document_id=f"d{i}") for i, c in enumerate(CITES * 3)]
    await _run(store, conv.default_branch_id, items=items)

    history = await store.get_history(conv.default_branch_id)
    assert [c["document_id"] for c in history[-1].citations] == [
        f"d{i}" for i in range(6)
    ]
    await engine.dispose()


async def test_ungrounded_reply_carries_no_citations():
    """The relevance gate staying shut is the feature working. It must not
    leave an empty-but-present sources block on the answer."""
    store, engine = await _db_store()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    await _run(store, conv.default_branch_id, items=[])

    history = await store.get_history(conv.default_branch_id)
    assert history[-1].citations == []
    await engine.dispose()


async def test_citations_are_inherited_across_a_fork():
    """`get_history` crosses branch boundaries; the hydration must cross with
    it, or a forked thread shows its inherited answers stripped of evidence."""
    store, engine = await _db_store()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    await _run(store, conv.default_branch_id)
    trunk = await store.get_history(conv.default_branch_id)

    fork = await store.create_branch(
        conversation_id=conv.id, from_node_id=trunk[-1].id, name="alt"
    )
    await _run(store, fork.id, prompt="and on the other hand?", items=[])

    history = await store.get_history(fork.id)
    inherited = history[1]
    assert inherited.role == "assistant"
    assert [c["filename"] for c in inherited.citations] == ["spec.pdf", "runbook.md"]
    await engine.dispose()


async def test_untraceable_citations_are_dropped():
    """A hit with no document id cannot be followed back to anything, so it is
    not a citation — persisting it would put an unclickable chip on an answer
    and imply evidence that cannot be produced."""
    store, engine = await _db_store()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    await _run(
        store,
        conv.default_branch_id,
        items=[{"filename": "ghost.pdf", "chunk_index": 0, "score": 0.9}, CITES[0]],
    )

    history = await store.get_history(conv.default_branch_id)
    assert [c["document_id"] for c in history[-1].citations] == ["d1"]
    await engine.dispose()


async def test_excerpts_are_bounded():
    """One reply's sources must not be able to dwarf the reply itself in every
    history response for the rest of the thread's life."""
    store, engine = await _db_store()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    await _run(store, conv.default_branch_id, items=[dict(CITES[0], excerpt="x" * 9000)])

    history = await store.get_history(conv.default_branch_id)
    assert len(history[-1].citations[0]["excerpt"]) == 600
    await engine.dispose()


# ── the exports ──────────────────────────────────────────────────────────────
# Citations reaching the screen is half the fix. The other half is that the
# artifact which *leaves* the product carries them — a decision report whose
# conclusions have no visible evidence is the copy-paste problem the export
# exists to replace, wearing a nicer font.

import api.conversation.router as router_mod
from starlette.testclient import TestClient

from api.main import app


class _GroundedIndex:
    """Stands in for DocumentIndex: every turn grounds on two known sources."""

    async def grounding_block(self, workspace_id, history):
        return ("[sources]", list(CITES))


@pytest.fixture
def grounded(monkeypatch):
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())
    monkeypatch.setattr(router_mod, "_documents", _GroundedIndex())


def _conv(client, headers, wid, **kw):
    resp = client.post(
        "/conversations", json={"workspace_id": wid, "title": "Grounded", **kw}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_history_returns_persisted_citations(make_workspace, grounded):
    """The reload path over real HTTP."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _conv(client, headers, wid)["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages",
            json={"prompt": "what does the spec say?"},
            headers=headers,
        )

        history = client.get(
            f"/conversations/branches/{branch_id}/history", headers=headers
        )
        assert history.status_code == 200
        reply = history.json()["nodes"][-1]
        assert [c["filename"] for c in reply["citations"]] == ["spec.pdf", "runbook.md"]


def test_branch_export_carries_its_sources(make_workspace, grounded):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "ping"}, headers=headers
        )

        md = client.get(
            f"/conversations/{cid}/export",
            params={"branch": branch_id, "format": "md"},
            headers=headers,
        ).text
        assert "Grounded on:" in md
        assert "spec.pdf §3" in md  # chunk_index 2 renders as part 3, 1-based
        assert "runbook.md §1" in md

        js = client.get(
            f"/conversations/{cid}/export",
            params={"branch": branch_id, "format": "json"},
            headers=headers,
        ).json()
        reply = js["nodes"][-1]
        assert [c["document_id"] for c in reply["citations"]] == ["d1", "d2"]


def test_decision_report_carries_its_sources(make_workspace, grounded):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "ping"}, headers=headers
        )

        md = client.get(f"/conversations/{cid}/export", headers=headers).text
        assert "Grounded on:" in md and "spec.pdf §3" in md

        js = client.get(
            f"/conversations/{cid}/export", params={"format": "json"}, headers=headers
        ).json()
        turns = js["explorations"][0]["turns"]
        sources = [s for t in turns for s in t["sources"]]
        assert [s["filename"] for s in sources] == ["spec.pdf", "runbook.md"]
        assert sources[0]["part"] == 3
