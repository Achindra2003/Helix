"""HTTP-level tests for the conversation routes (E2 wiring + server-side RBAC).

Drives the real FastAPI app with the stub provider through `TestClient`.
Identity/membership live in the (hermetic) test DB via the real auth routes;
conversation data uses a fresh in-memory store per test. Every route is gated:
these tests prove both the streaming pipeline and the RBAC/tenancy boundary.
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
    the HTTP-wiring tests stay fast and never touch the DB file for nodes."""
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _parse_sse(body: str) -> list[str]:
    """Return the `data:` payloads from an SSE response body, in order."""
    return [
        line[len("data: ") :]
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def _create_conv(client, headers, workspace_id, **overrides):
    payload = {"workspace_id": workspace_id, "title": "demo", **overrides}
    resp = client.post("/conversations", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_create_then_stream_send(make_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]

        resp = client.post(
            f"/conversations/{branch_id}/messages",
            json={"prompt": "hello"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        payloads = _parse_sse(resp.text)
        assert payloads[-1] == "[DONE]"

        events = [json.loads(p) for p in payloads if p != "[DONE]"]
        kinds = [e["kind"] for e in events]
        assert kinds[0] == "user_node"
        assert kinds[-1] == "assistant_node"
        assert "token" in kinds
        # Identity is server-derived: the persisted author is the JWT user,
        # regardless of anything the client might claim.
        assert events[0]["node"]["author_id"] == uid


def test_send_to_unknown_branch_is_404(make_workspace):
    with TestClient(app) as client:
        headers, _, _ = make_workspace(client)
        resp = client.post(
            "/conversations/nope/messages", json={"prompt": "x"}, headers=headers
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


def test_routes_require_auth():
    """No token -> 401 on every conversation surface (server-side FR-3)."""
    with TestClient(app) as client:
        assert client.post("/conversations", json={"workspace_id": "w"}).status_code == 401
        assert client.get("/conversations", params={"workspace_id": "w"}).status_code == 401
        assert client.get("/conversations/some-id").status_code == 401
        assert client.post("/conversations/b/messages", json={"prompt": "x"}).status_code == 401
        assert client.post("/conversations/b/deep", json={"prompt": "x"}).status_code == 401
        assert client.post("/conversations/c/fork", json={"from_node_id": "n"}).status_code == 401


def test_non_member_cannot_see_or_touch_conversations(make_workspace, make_user):
    """Tenancy: a user outside the workspace gets 404s (not even existence)."""
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        created = _create_conv(client, owner_headers, wid)
        conv_id, branch_id = created["conversation_id"], created["branch_id"]

        outsider_headers, _ = make_user(client)
        assert (
            client.get("/conversations", params={"workspace_id": wid}, headers=outsider_headers)
        ).status_code == 404
        assert client.get(f"/conversations/{conv_id}", headers=outsider_headers).status_code == 404
        assert (
            client.post(
                f"/conversations/{branch_id}/messages",
                json={"prompt": "hi"},
                headers=outsider_headers,
            )
        ).status_code == 404
        assert (
            client.get(f"/conversations/branches/{branch_id}/history", headers=outsider_headers)
        ).status_code == 404


def test_observer_reads_but_cannot_write(make_workspace, join_workspace):
    """Observer: full read access, 403 on send/fork/create/references (FR-3)."""
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        created = _create_conv(client, owner_headers, wid)
        conv_id, branch_id = created["conversation_id"], created["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages",
            json={"prompt": "seed turn"},
            headers=owner_headers,
        )

        obs_headers, _ = join_workspace(client, owner_headers, wid, role="observer")

        # Reads are open to observers.
        listed = client.get(
            "/conversations", params={"workspace_id": wid}, headers=obs_headers
        )
        assert listed.status_code == 200 and len(listed.json()["items"]) == 1
        hist = client.get(
            f"/conversations/branches/{branch_id}/history", headers=obs_headers
        )
        assert hist.status_code == 200 and len(hist.json()["nodes"]) == 2

        # Writes are forbidden.
        assert (
            client.post(
                f"/conversations/{branch_id}/messages",
                json={"prompt": "hi"},
                headers=obs_headers,
            )
        ).status_code == 403
        node_id = hist.json()["nodes"][0]["id"]
        assert (
            client.post(
                f"/conversations/{conv_id}/fork",
                json={"from_node_id": node_id, "name": "alt"},
                headers=obs_headers,
            )
        ).status_code == 403
        assert (
            client.post(
                "/conversations",
                json={"workspace_id": wid, "title": "mine"},
                headers=obs_headers,
            )
        ).status_code == 403
        assert (
            client.post(
                f"/conversations/{branch_id}/deep",
                json={"prompt": "hard"},
                headers=obs_headers,
            )
        ).status_code == 403


def test_fork_and_history_endpoints(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _create_conv(client, headers, wid)
        conv_id, branch_id = created["conversation_id"], created["branch_id"]

        # One full turn so there's a node to fork from.
        client.post(
            f"/conversations/{branch_id}/messages",
            json={"prompt": "hello"},
            headers=headers,
        )

        history = client.get(
            f"/conversations/branches/{branch_id}/history", headers=headers
        ).json()
        nodes = history["nodes"]
        assert [n["role"] for n in nodes] == ["user", "assistant"]

        # Fork off the user node; the fork inherits history up to that point.
        user_node_id = nodes[0]["id"]
        forked = client.post(
            f"/conversations/{conv_id}/fork",
            json={"from_node_id": user_node_id, "name": "alt"},
            headers=headers,
        )
        assert forked.status_code == 200
        fork_branch_id = forked.json()["branch_id"]

        fork_hist = client.get(
            f"/conversations/branches/{fork_branch_id}/history", headers=headers
        ).json()
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


def test_escalate_deep_reasoning_streams_trace(monkeypatch, make_workspace):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(
        router_mod,
        "build_ouroboros_graph",
        lambda **kw: (_FakeGraph(), {}, lambda seed: {"seed": seed}, lambda: 1234),
    )

    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid, title="deep")["branch_id"]
        resp = client.post(
            f"/conversations/{branch_id}/deep",
            json={"prompt": "hard question"},
            headers=headers,
        )
        assert resp.status_code == 200

        payloads = _parse_sse(resp.text)
        assert payloads[-1] == "[DONE]"
        kinds = [json.loads(p)["kind"] for p in payloads if p != "[DONE]"]
        assert "step" in kinds and "budget" in kinds and "complete" in kinds
        # Every deep run now opens with its run_id handle (reconnect/kill),
        # then the usual user_node ... assistant_node envelope.
        assert kinds[0] == "deep_run" and kinds[1] == "user_node"
        assert kinds[-1] == "assistant_node"


def test_escalate_without_groq_key_is_503(monkeypatch, make_workspace):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "")
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid, title="deep")["branch_id"]
        resp = client.post(
            f"/conversations/{branch_id}/deep", json={"prompt": "x"}, headers=headers
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "deep_reasoning_unavailable"


def test_list_conversations_scoped_to_workspace(make_workspace):
    with TestClient(app) as client:
        headers_a, _, wid_a = make_workspace(client)
        headers_b, _, wid_b = make_workspace(client)
        _create_conv(client, headers_a, wid_a, title="one")
        _create_conv(client, headers_a, wid_a, title="two")
        _create_conv(client, headers_b, wid_b, title="other")

        a = client.get("/conversations", params={"workspace_id": wid_a}, headers=headers_a)
        assert a.status_code == 200
        assert sorted(c["title"] for c in a.json()["items"]) == ["one", "two"]
        b = client.get("/conversations", params={"workspace_id": wid_b}, headers=headers_b)
        assert [c["title"] for c in b.json()["items"]] == ["other"]  # no cross-tenant leak


def test_private_conversations_are_scoped_to_their_author(make_workspace, join_workspace):
    with TestClient(app) as client:
        alice_headers, _, wid = make_workspace(client)
        _create_conv(client, alice_headers, wid, title="team", visibility="shared")
        secret = _create_conv(
            client, alice_headers, wid, title="alice-secret", visibility="private"
        )

        # Bob (a member) sees the shared one but NOT alice's private one.
        bob_headers, _ = join_workspace(client, alice_headers, wid)
        bob = client.get("/conversations", params={"workspace_id": wid}, headers=bob_headers)
        assert sorted(c["title"] for c in bob.json()["items"]) == ["team"]
        # Direct fetch of the private conversation is 404 for bob (no probing).
        assert (
            client.get(f"/conversations/{secret['conversation_id']}", headers=bob_headers)
        ).status_code == 404
        assert (
            client.post(
                f"/conversations/{secret['branch_id']}/messages",
                json={"prompt": "hi"},
                headers=bob_headers,
            )
        ).status_code == 404

        # Alice sees both her shared and her own private conversation.
        alice = client.get(
            "/conversations", params={"workspace_id": wid}, headers=alice_headers
        )
        assert sorted(c["title"] for c in alice.json()["items"]) == ["alice-secret", "team"]


def test_cross_conversation_reference_link_lifecycle_and_guards(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        mine = _create_conv(client, headers, wid, title="mine")["conversation_id"]
        source = _create_conv(
            client, headers, wid, title="source", visibility="shared"
        )["conversation_id"]

        # Link the shared source thread in -> it shows up as a reference.
        added = client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": source},
            headers=headers,
        )
        assert added.status_code == 201
        assert [r["title"] for r in added.json()["items"]] == ["source"]
        assert (
            client.get(f"/conversations/{mine}/references", headers=headers)
        ).json()["items"][0]["id"] == source

        # Linking again is idempotent (no duplicate).
        again = client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": source},
            headers=headers,
        )
        assert len(again.json()["items"]) == 1

        # Unlink -> empty again.
        removed = client.delete(
            f"/conversations/{mine}/references/{source}", headers=headers
        )
        assert removed.status_code == 200 and removed.json()["items"] == []


def test_reference_guards_reject_self_private_and_cross_workspace(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        mine = _create_conv(client, headers, wid, title="mine")["conversation_id"]

        # Self-reference is rejected.
        assert client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": mine},
            headers=headers,
        ).status_code == 400

        # A private conversation cannot be referenced.
        priv = _create_conv(
            client, headers, wid, title="secret", visibility="private"
        )["conversation_id"]
        assert client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": priv},
            headers=headers,
        ).status_code == 403

        # A shared conversation in a *different* workspace cannot be referenced.
        headers2, _, wid2 = make_workspace(client)
        other_ws = _create_conv(
            client, headers2, wid2, title="elsewhere", visibility="shared"
        )["conversation_id"]
        assert client.post(
            f"/conversations/{mine}/references",
            json={"referenced_conversation_id": other_ws},
            headers=headers,
        ).status_code == 400


def test_get_conversation_and_404(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        cid = _create_conv(client, headers, wid, title="get me")["conversation_id"]
        ok = client.get(f"/conversations/{cid}", headers=headers)
        assert ok.status_code == 200 and ok.json()["title"] == "get me"
        assert client.get("/conversations/nope", headers=headers).status_code == 404


def test_branch_tree_lists_main_and_fork(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _create_conv(client, headers, wid, title="tree")
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "hi"}, headers=headers
        )
        node_id = client.get(
            f"/conversations/branches/{branch_id}/history", headers=headers
        ).json()["nodes"][-1]["id"]
        client.post(
            f"/conversations/{cid}/fork",
            json={"from_node_id": node_id, "name": "alt"},
            headers=headers,
        )

        tree = client.get(f"/conversations/{cid}/branches", headers=headers)
        assert tree.status_code == 200
        assert sorted(b["name"] for b in tree.json()["items"]) == ["alt", "main"]
        alt = next(b for b in tree.json()["items"] if b["name"] == "alt")
        assert alt["parent_branch_id"] == branch_id  # lineage link present


def test_export_markdown_and_json(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _create_conv(client, headers, wid, title="Export Me")
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "ping"}, headers=headers
        )

        md = client.get(
            f"/conversations/{cid}/export",
            params={"branch": branch_id, "format": "md"},
            headers=headers,
        )
        assert md.status_code == 200
        assert md.headers["content-type"].startswith("text/markdown")
        assert "# Export Me" in md.text and "ping" in md.text

        js = client.get(
            f"/conversations/{cid}/export",
            params={"branch": branch_id, "format": "json"},
            headers=headers,
        )
        assert js.status_code == 200
        body = js.json()
        assert body["conversation"]["title"] == "Export Me"
        assert any(n["content"] == "ping" for n in body["nodes"])


class _PausingGraph:
    """Fake graph for the guided (steerable) flow: pauses at steer once, then
    completes after a resume that carries the injected guidance."""

    def __init__(self):
        self.updates = []
        self.resumed = False

    async def astream(self, inputs, config, stream_mode):
        if inputs is not None:  # first segment -> will pause
            yield ("updates", {"think": {"depth": 1, "energy": 70.0, "thought": "draft"}})
            yield ("updates", {"synthesize": {"synthesis": "draft answer", "confidence": 0.5}})
        else:  # resumed from checkpoint
            yield ("messages", (_Chunk("Steered answer."), {"langgraph_node": "surface"}))
            yield ("updates", {"surface": {"surfaced_insight": "Steered answer.", "stop_reason": "converged"}})

    async def aget_state(self, config):
        return SimpleNamespace(next=() if self.resumed else ("steer",))

    async def aupdate_state(self, config, values):
        self.resumed = True
        self.updates.append(values)


def test_steerable_deep_run_pauses_then_resumes_with_guidance(monkeypatch, make_workspace):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    fake = _PausingGraph()
    monkeypatch.setattr(
        router_mod,
        "build_ouroboros_graph",
        lambda **kw: (fake, {}, lambda seed: {"seed": seed}, lambda: 42),
    )

    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid, title="guided")["branch_id"]

        # Segment 1: the run streams, then pauses at the steer checkpoint.
        resp = client.post(
            f"/conversations/{branch_id}/deep",
            json={"prompt": "hard question", "steerable": True},
            headers=headers,
        )
        assert resp.status_code == 200
        events = [json.loads(p) for p in _parse_sse(resp.text)]
        kinds = [e["kind"] for e in events]
        assert kinds[0] == "deep_run"          # the run-control handle
        run_id = events[0]["run_id"]
        assert "waiting" in kinds              # paused for human input
        assert "assistant_node" not in kinds   # no empty reply persisted
        hist = client.get(
            f"/conversations/branches/{branch_id}/history", headers=headers
        ).json()["nodes"]
        assert [n["role"] for n in hist] == ["user"]

        # Segment 2: steer with guidance -> run completes, reply persisted.
        resumed = client.post(
            f"/conversations/deep/runs/{run_id}/steer",
            json={"guidance": "optimize for shipping speed"},
            headers=headers,
        )
        assert resumed.status_code == 200
        r_events = [json.loads(p) for p in _parse_sse(resumed.text) if p != "[DONE]"]
        r_kinds = [e["kind"] for e in r_events]
        assert "token" in r_kinds and "assistant_node" in r_kinds
        assert fake.updates == [{"human_input": "optimize for shipping speed"}]

        hist = client.get(
            f"/conversations/branches/{branch_id}/history", headers=headers
        ).json()["nodes"]
        assert [n["role"] for n in hist] == ["user", "assistant"]
        assert hist[-1]["content"] == "Steered answer."

        # The run is finished. Its handle is *retained* now (reconnect surface),
        # so steering it is a clear conflict rather than a vanished 404.
        gone = client.post(
            f"/conversations/deep/runs/{run_id}/steer",
            json={"guidance": "again"},
            headers=headers,
        )
        assert gone.status_code == 409


def test_steer_requires_workspace_membership(monkeypatch, make_workspace, make_user):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    fake = _PausingGraph()
    monkeypatch.setattr(
        router_mod,
        "build_ouroboros_graph",
        lambda **kw: (fake, {}, lambda seed: {"seed": seed}, lambda: 42),
    )
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid, title="guided")["branch_id"]
        resp = client.post(
            f"/conversations/{branch_id}/deep",
            json={"prompt": "q", "steerable": True},
            headers=headers,
        )
        run_id = json.loads(_parse_sse(resp.text)[0])["run_id"]

        outsider, _ = make_user(client)
        denied = client.post(
            f"/conversations/deep/runs/{run_id}/steer",
            json={"guidance": "hijack"},
            headers=outsider,
        )
        assert denied.status_code == 404  # not even existence is leaked


def test_deep_run_reconnect_status_and_kill_endpoints(monkeypatch, make_workspace, make_user):
    """The background-run surface: status poll, stream reattach, kill, RBAC."""
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(
        router_mod,
        "build_ouroboros_graph",
        lambda **kw: (_FakeGraph(), {}, lambda seed: {"seed": seed}, lambda: 1234),
    )
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid, title="deep")["branch_id"]
        resp = client.post(
            f"/conversations/{branch_id}/deep",
            json={"prompt": "hard question"},
            headers=headers,
        )
        first = json.loads(_parse_sse(resp.text)[0])
        assert first["kind"] == "deep_run"
        run_id = first["run_id"]

        # Status: the run finished server-side; seq counts the whole log.
        st = client.get(
            f"/conversations/deep/runs/{run_id}/status", headers=headers
        ).json()
        assert st["status"] == "done"
        assert st["seq"] > 3
        assert st["queue_position"] is None

        # Reconnect: full replay, well-formed, ends with [DONE].
        replay = client.get(
            f"/conversations/deep/runs/{run_id}/stream", headers=headers
        )
        payloads = _parse_sse(replay.text)
        assert payloads[-1] == "[DONE]"
        kinds = [json.loads(p)["kind"] for p in payloads if p != "[DONE]"]
        assert kinds[0] == "deep_run" and "assistant_node" in kinds

        # Reconnect from the end: nothing left to replay, stream ends clean.
        tail = client.get(
            f"/conversations/deep/runs/{run_id}/stream?after={st['seq']}",
            headers=headers,
        )
        assert _parse_sse(tail.text) == []

        # Kill on a finished run is a no-op that reports the settled status.
        killed = client.post(
            f"/conversations/deep/runs/{run_id}/kill", headers=headers
        ).json()
        assert killed["status"] == "done"

        # RBAC: an outsider can't even learn the run exists.
        outsider, _ = make_user(client)
        assert (
            client.get(
                f"/conversations/deep/runs/{run_id}/status", headers=outsider
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/conversations/deep/runs/{run_id}/kill", headers=outsider
            ).status_code
            == 404
        )


def test_delete_last_message_removes_the_trailing_turn(make_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "hi"}, headers=headers
        )

        deleted = client.delete(f"/conversations/{branch_id}/messages/last", headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert len(deleted.json()["removed_ids"]) == 2  # user + assistant

        hist = client.get(f"/conversations/branches/{branch_id}/history", headers=headers)
        assert hist.json()["nodes"] == []


def test_delete_last_message_is_author_gated(make_workspace, join_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, headers, wid)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "hi"}, headers=headers
        )

        denied = client.delete(
            f"/conversations/{branch_id}/messages/last", headers=member_headers
        )
        assert denied.status_code == 403


def test_delete_last_message_blocked_after_a_fork(make_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        conv = _create_conv(client, headers, wid)
        branch_id, conversation_id = conv["branch_id"], conv["conversation_id"]
        client.post(
            f"/conversations/{branch_id}/messages", json={"prompt": "hi"}, headers=headers
        )
        head_node_id = client.get(
            f"/conversations/branches/{branch_id}/history", headers=headers
        ).json()["nodes"][-1]["id"]

        fork = client.post(
            f"/conversations/{conversation_id}/fork",
            json={"from_node_id": head_node_id, "name": "alt"},
            headers=headers,
        )
        assert fork.status_code == 200, fork.text

        blocked = client.delete(f"/conversations/{branch_id}/messages/last", headers=headers)
        assert blocked.status_code == 409


def test_rename_and_delete_conversation_author_or_owner_only(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _oid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, owner_headers, wid)

        # A collaborator's conversation…
        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "draft", "visibility": "shared"},
            headers=member_headers,
        ).json()
        cid = conv["conversation_id"]

        # …its author can rename it…
        renamed = client.patch(
            f"/conversations/{cid}", json={"title": "final"}, headers=member_headers
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "final"

        # …a second collaborator cannot…
        other_headers, _xid = join_workspace(client, owner_headers, wid)
        denied = client.patch(
            f"/conversations/{cid}", json={"title": "hijack"}, headers=other_headers
        )
        assert denied.status_code == 403
        assert client.delete(f"/conversations/{cid}", headers=other_headers).status_code == 403

        # …but the workspace owner can delete it.
        deleted = client.delete(f"/conversations/{cid}", headers=owner_headers)
        assert deleted.status_code == 200, deleted.text
        assert client.get(f"/conversations/{cid}", headers=owner_headers).status_code == 404


def test_branch_rename_and_delete_with_safety(make_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        conv = _create_conv(client, headers, wid)
        main_id, cid = conv["branch_id"], conv["conversation_id"]
        client.post(f"/conversations/{main_id}/messages", json={"prompt": "hi"}, headers=headers)
        node_id = client.get(
            f"/conversations/branches/{main_id}/history", headers=headers
        ).json()["nodes"][-1]["id"]
        fork = client.post(
            f"/conversations/{cid}/fork",
            json={"from_node_id": node_id, "name": "experiment"},
            headers=headers,
        ).json()

        renamed = client.patch(
            f"/conversations/branches/{fork['branch_id']}", json={"name": "spike"}, headers=headers
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "spike"

        # Main is protected; the fork deletes cleanly.
        assert client.delete(f"/conversations/branches/{main_id}", headers=headers).status_code == 409
        gone = client.delete(f"/conversations/branches/{fork['branch_id']}", headers=headers)
        assert gone.status_code == 200, gone.text
        tree = client.get(f"/conversations/{cid}/branches", headers=headers).json()["items"]
        assert [b["id"] for b in tree] == [main_id]
