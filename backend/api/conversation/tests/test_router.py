"""HTTP-level test for the conversation SSE endpoint (E2 wiring).

Drives the real FastAPI app with the stub provider (the default) through
`TestClient`, proving the create -> send -> stream path emits well-formed SSE
frames ending in the `[DONE]` sentinel.
"""
import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import api.conversation.router as router_mod
from api.conversation.store import InMemoryStore
from api.main import app


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    """Swap the router's durable store for a fresh in-memory one per test, so
    the HTTP-wiring tests stay fast and never touch the dev SQLite file."""
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _parse_sse(body: str) -> list[str]:
    """Return the `data:` payloads from an SSE response body, in order."""
    return [
        line[len("data: ") :]
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def test_create_then_stream_send():
    with TestClient(app) as client:
        created = client.post("/conversations", json={"title": "demo"})
        assert created.status_code == 200
        branch_id = created.json()["branch_id"]

        resp = client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "hello"}
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        payloads = _parse_sse(resp.text)
        assert payloads[-1] == "[DONE]"

        kinds = [json.loads(p)["kind"] for p in payloads if p != "[DONE]"]
        assert kinds[0] == "user_node"
        assert kinds[-1] == "assistant_node"
        assert "token" in kinds


def test_send_to_unknown_branch_is_404():
    with TestClient(app) as client:
        resp = client.post("/conversations/nope/messages", json={"prompt": "x"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


def test_fork_and_history_endpoints():
    with TestClient(app) as client:
        created = client.post("/conversations", json={"title": "demo"}).json()
        conv_id, branch_id = created["conversation_id"], created["branch_id"]

        # One full turn so there's a node to fork from.
        client.post(f"/conversations/{branch_id}/messages", json={"prompt": "hello"})

        history = client.get(f"/conversations/branches/{branch_id}/history").json()
        nodes = history["nodes"]
        assert [n["role"] for n in nodes] == ["user", "assistant"]

        # Fork off the user node; the fork inherits history up to that point.
        user_node_id = nodes[0]["id"]
        forked = client.post(
            f"/conversations/{conv_id}/fork",
            json={"from_node_id": user_node_id, "name": "alt"},
        )
        assert forked.status_code == 200
        fork_branch_id = forked.json()["branch_id"]

        fork_hist = client.get(f"/conversations/branches/{fork_branch_id}/history").json()
        assert [n["role"] for n in fork_hist["nodes"]] == ["user"]  # no assistant copied


class _Chunk:
    def __init__(self, content):
        self.content = content


class _FakeGraph:
    """Stands in for a compiled Ouroboros graph (no network/LangGraph needed)."""

    async def astream(self, inputs, config, stream_mode):
        yield ("updates", {"think": {"depth": 1, "energy": 70.0, "thought": "t"}})
        yield ("messages", (_Chunk("Decisive answer."), {"langgraph_node": "surface"}))
        yield ("updates", {"surface": {"surfaced_insight": "Decisive answer.", "stop_reason": "converged"}})

    async def aget_state(self, config):
        return SimpleNamespace(next=())


def test_escalate_deep_reasoning_streams_trace(monkeypatch):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(
        router_mod,
        "build_ouroboros_graph",
        lambda **kw: (_FakeGraph(), {}, lambda seed: {"seed": seed}, lambda: 1234),
    )

    with TestClient(app) as client:
        branch_id = client.post("/conversations", json={"title": "deep"}).json()["branch_id"]
        resp = client.post(f"/conversations/{branch_id}/deep", json={"prompt": "hard question"})
        assert resp.status_code == 200

        payloads = [
            line[len("data: ") :]
            for line in resp.text.splitlines()
            if line.startswith("data: ")
        ]
        assert payloads[-1] == "[DONE]"
        kinds = [json.loads(p)["kind"] for p in payloads if p != "[DONE]"]
        assert "step" in kinds and "budget" in kinds and "complete" in kinds
        assert kinds[0] == "user_node" and kinds[-1] == "assistant_node"


def test_escalate_without_groq_key_is_503(monkeypatch):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "")
    with TestClient(app) as client:
        branch_id = client.post("/conversations", json={"title": "deep"}).json()["branch_id"]
        resp = client.post(f"/conversations/{branch_id}/deep", json={"prompt": "x"})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "deep_reasoning_unavailable"


def test_list_conversations_scoped_to_workspace():
    with TestClient(app) as client:
        client.post("/conversations", json={"workspace_id": "wA", "title": "one"})
        client.post("/conversations", json={"workspace_id": "wA", "title": "two"})
        client.post("/conversations", json={"workspace_id": "wB", "title": "other"})

        a = client.get("/conversations", params={"workspace_id": "wA"})
        assert a.status_code == 200
        assert sorted(c["title"] for c in a.json()["items"]) == ["one", "two"]
        b = client.get("/conversations", params={"workspace_id": "wB"})
        assert [c["title"] for c in b.json()["items"]] == ["other"]  # no cross-tenant leak


def test_private_conversations_are_scoped_to_their_author():
    with TestClient(app) as client:
        client.post(
            "/conversations",
            json={"workspace_id": "w", "author_id": "alice", "title": "team", "visibility": "shared"},
        )
        client.post(
            "/conversations",
            json={"workspace_id": "w", "author_id": "alice", "title": "alice-secret", "visibility": "private"},
        )

        # Bob (a different member) sees the shared one but NOT alice's private one.
        bob = client.get("/conversations", params={"workspace_id": "w", "viewer_id": "bob"})
        assert sorted(c["title"] for c in bob.json()["items"]) == ["team"]

        # Alice sees both her shared and her own private conversation.
        alice = client.get("/conversations", params={"workspace_id": "w", "viewer_id": "alice"})
        assert sorted(c["title"] for c in alice.json()["items"]) == ["alice-secret", "team"]

        # Omitting viewer_id returns everything (engine/admin path, unchanged).
        all_ = client.get("/conversations", params={"workspace_id": "w"})
        assert len(all_.json()["items"]) == 2


def test_cross_conversation_reference_link_lifecycle_and_guards():
    with TestClient(app) as client:
        mine = client.post(
            "/conversations", json={"workspace_id": "w", "title": "mine"}
        ).json()["conversation_id"]
        source = client.post(
            "/conversations",
            json={"workspace_id": "w", "title": "source", "visibility": "shared"},
        ).json()["conversation_id"]

        # Link the shared source thread in -> it shows up as a reference.
        added = client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": source},
        )
        assert added.status_code == 201
        assert [r["title"] for r in added.json()["items"]] == ["source"]
        assert client.get(f"/conversations/{mine}/references").json()["items"][0]["id"] == source

        # Linking again is idempotent (no duplicate).
        again = client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": source},
        )
        assert len(again.json()["items"]) == 1

        # Unlink -> empty again.
        removed = client.delete(f"/conversations/{mine}/references/{source}")
        assert removed.status_code == 200 and removed.json()["items"] == []


def test_reference_guards_reject_self_private_and_cross_workspace():
    with TestClient(app) as client:
        mine = client.post(
            "/conversations", json={"workspace_id": "w", "title": "mine"}
        ).json()["conversation_id"]

        # Self-reference is rejected.
        assert client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": mine},
        ).status_code == 400

        # A private conversation cannot be referenced.
        priv = client.post(
            "/conversations",
            json={"workspace_id": "w", "title": "secret", "visibility": "private"},
        ).json()["conversation_id"]
        assert client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": priv},
        ).status_code == 403

        # A shared conversation in a *different* workspace cannot be referenced.
        other_ws = client.post(
            "/conversations",
            json={"workspace_id": "other", "title": "elsewhere", "visibility": "shared"},
        ).json()["conversation_id"]
        assert client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": other_ws},
        ).status_code == 400


def test_get_conversation_and_404():
    with TestClient(app) as client:
        cid = client.post("/conversations", json={"title": "get me"}).json()["conversation_id"]
        ok = client.get(f"/conversations/{cid}")
        assert ok.status_code == 200 and ok.json()["title"] == "get me"
        assert client.get("/conversations/nope").status_code == 404


def test_branch_tree_lists_main_and_fork():
    with TestClient(app) as client:
        created = client.post("/conversations", json={"title": "tree"}).json()
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(f"/conversations/{branch_id}/messages", json={"prompt": "hi"})
        node_id = client.get(f"/conversations/branches/{branch_id}/history").json()["nodes"][-1]["id"]
        client.post(f"/conversations/{cid}/fork", json={"from_node_id": node_id, "name": "alt"})

        tree = client.get(f"/conversations/{cid}/branches")
        assert tree.status_code == 200
        assert sorted(b["name"] for b in tree.json()["items"]) == ["alt", "main"]
        alt = next(b for b in tree.json()["items"] if b["name"] == "alt")
        assert alt["parent_branch_id"] == branch_id  # lineage link present


def test_export_markdown_and_json():
    with TestClient(app) as client:
        created = client.post("/conversations", json={"title": "Export Me"}).json()
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(f"/conversations/{branch_id}/messages", json={"prompt": "ping"})

        md = client.get(f"/conversations/{cid}/export", params={"branch": branch_id, "format": "md"})
        assert md.status_code == 200
        assert md.headers["content-type"].startswith("text/markdown")
        assert "# Export Me" in md.text and "ping" in md.text

        js = client.get(f"/conversations/{cid}/export", params={"branch": branch_id, "format": "json"})
        assert js.status_code == 200
        body = js.json()
        assert body["conversation"]["title"] == "Export Me"
        assert any(n["content"] == "ping" for n in body["nodes"])
