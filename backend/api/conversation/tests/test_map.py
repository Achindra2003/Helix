"""Workspace Map tests: the aggregate graph read + the `viewing` presence frame.

Same harness as the other route tests — real FastAPI app, hermetic auth via the
conftest fixtures, fresh in-memory conversation store per test.
"""
import json

import pytest
from starlette.testclient import TestClient

import api.conversation.router as router_mod
from api.conversation.store import InMemoryStore
from api.main import app


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _token(headers: dict) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def _create_conv(client, headers, workspace_id, **overrides):
    payload = {"workspace_id": workspace_id, "title": "demo", **overrides}
    resp = client.post("/conversations", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_map_requires_auth_and_membership(make_workspace, make_user):
    with TestClient(app) as client:
        _, _, wid = make_workspace(client)
        assert client.get(f"/workspaces/{wid}/map").status_code == 401
        outsider, _ = make_user(client)
        assert (
            client.get(f"/workspaces/{wid}/map", headers=outsider).status_code == 404
        )


def test_map_aggregates_branches_nodes_and_references(make_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)

        a = _create_conv(client, headers, wid, title="alpha")
        b = _create_conv(client, headers, wid, title="beta")

        # One turn on alpha, then fork from its user node.
        client.post(
            f"/conversations/{a['branch_id']}/messages",
            json={"prompt": "hello"},
            headers=headers,
        )
        hist = client.get(
            f"/conversations/branches/{a['branch_id']}/history", headers=headers
        ).json()["nodes"]
        fork = client.post(
            f"/conversations/{a['conversation_id']}/fork",
            json={"from_node_id": hist[0]["id"], "name": "alt"},
            headers=headers,
        ).json()
        # alpha references beta.
        client.post(
            f"/conversations/{a['conversation_id']}/references",
            json={"referenced_conversation_id": b["conversation_id"]},
            headers=headers,
        )

        graph = client.get(f"/workspaces/{wid}/map", headers=headers).json()
        convs = {c["id"]: c for c in graph["conversations"]}
        alpha = convs[a["conversation_id"]]

        assert sorted(br["name"] for br in alpha["branches"]) == ["alt", "main"]
        alt = next(br for br in alpha["branches"] if br["name"] == "alt")
        assert alt["parent_branch_id"] == a["branch_id"]
        assert alt["fork_node_id"] == hist[0]["id"]

        # Nodes are the lean skeleton: deduped across fork histories, no content.
        assert len(alpha["nodes"]) == 2  # user + assistant, each once
        node = alpha["nodes"][0]
        assert set(node) == {"id", "branch_id", "parent_id", "seq", "role", "author_id"}
        assert node["author_id"] == uid

        assert alpha["references"] == [b["conversation_id"]]
        assert convs[b["conversation_id"]]["nodes"] == []


def test_map_hides_others_private_threads(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        _create_conv(client, owner_headers, wid, title="open")
        _create_conv(
            client, owner_headers, wid, title="secret", visibility="private"
        )

        # The author's map has both; a teammate's map only the shared one.
        own = client.get(f"/workspaces/{wid}/map", headers=owner_headers).json()
        assert sorted(c["title"] for c in own["conversations"]) == ["open", "secret"]

        mate_headers, _ = join_workspace(client, owner_headers, wid)
        mate = client.get(f"/workspaces/{wid}/map", headers=mate_headers).json()
        assert [c["title"] for c in mate["conversations"]] == ["open"]


def test_viewing_presence_reaches_teammates(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, owner_id, wid = make_workspace(client)
        mate_headers, _ = join_workspace(client, owner_headers, wid)

        with client.websocket_connect(
            f"/ws/workspaces/{wid}?token={_token(owner_headers)}"
        ) as ws_owner:
            ws_owner.receive_text()  # own presence frame
            with client.websocket_connect(
                f"/ws/workspaces/{wid}?token={_token(mate_headers)}"
            ) as ws_mate:
                ws_owner.receive_text()  # mate-joined roster
                ws_mate.receive_text()

                # Owner reports the branch they're viewing; the mate's next
                # presence frame carries it.
                ws_owner.send_text(
                    json.dumps(
                        {
                            "kind": "viewing",
                            "branch_id": "branch-42",
                            "conversation_id": "conv-7",
                        }
                    )
                )
                frame = json.loads(ws_mate.receive_text())
                assert frame["kind"] == "presence"
                owner_entry = next(
                    u for u in frame["users"] if u["user_id"] == owner_id
                )
                assert owner_entry["viewing"] == "branch-42"
                assert owner_entry["viewing_conversation"] == "conv-7"

                # Clearing it (leave the thread) rebroadcasts null.
                ws_owner.send_text(json.dumps({"kind": "viewing", "branch_id": None}))
                frame = json.loads(ws_mate.receive_text())
                owner_entry = next(
                    u for u in frame["users"] if u["user_id"] == owner_id
                )
                assert owner_entry["viewing"] is None
