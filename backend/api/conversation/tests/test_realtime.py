"""Workspace realtime room tests (FR-5): auth gate, presence, live fan-out.

TestClient's websocket support runs the real ASGI app, so these exercise the
same code path a browser hits — token check, membership gate, roster
broadcasts, and the run-event relay from a streamed turn on a shared thread.
"""
import json

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import api.conversation.router as router_mod
from api.conversation.store import InMemoryStore
from api.main import app


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _token(headers: dict) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def test_ws_rejects_bad_token_and_non_member(make_workspace, make_user):
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)

        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/workspaces/{wid}?token=garbage"):
                pass
        assert exc.value.code == 4401

        outsider, _ = make_user(client)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                f"/ws/workspaces/{wid}?token={_token(outsider)}"
            ):
                pass
        assert exc.value.code == 4403


def test_presence_roster_tracks_joins_and_leaves(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, owner_id, wid = make_workspace(client)
        mate_headers, mate_id = join_workspace(client, owner_headers, wid)

        with client.websocket_connect(
            f"/ws/workspaces/{wid}?token={_token(owner_headers)}"
        ) as ws_owner:
            first = json.loads(ws_owner.receive_text())
            assert first["kind"] == "presence"
            assert [u["user_id"] for u in first["users"]] == [owner_id]

            with client.websocket_connect(
                f"/ws/workspaces/{wid}?token={_token(mate_headers)}"
            ) as ws_mate:
                # Both sockets see the two-person roster.
                joined = json.loads(ws_owner.receive_text())
                assert {u["user_id"] for u in joined["users"]} == {owner_id, mate_id}
                mate_view = json.loads(ws_mate.receive_text())
                assert {u["user_id"] for u in mate_view["users"]} == {owner_id, mate_id}

            # Teammate disconnects -> roster shrinks back.
            left = json.loads(ws_owner.receive_text())
            assert [u["user_id"] for u in left["users"]] == [owner_id]


def test_shared_turn_fans_out_to_teammate(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, owner_id, wid = make_workspace(client)
        mate_headers, _ = join_workspace(client, owner_headers, wid)

        created = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "shared thread"},
            headers=owner_headers,
        ).json()
        branch_id = created["branch_id"]

        with client.websocket_connect(
            f"/ws/workspaces/{wid}?token={_token(mate_headers)}"
        ) as ws_mate:
            ws_mate.receive_text()  # own presence frame

            resp = client.post(
                f"/conversations/{branch_id}/messages",
                json={"prompt": "hello team"},
                headers=owner_headers,
            )
            assert resp.status_code == 200

            kinds = []
            while True:
                frame = json.loads(ws_mate.receive_text())
                assert frame["kind"] == "run_event"
                assert frame["branch_id"] == branch_id
                assert frame["author_id"] == owner_id
                kinds.append(frame["event"]["kind"])
                if frame["event"]["kind"] == "done":
                    break
            assert kinds[0] == "user_node"
            assert "token" in kinds
            assert "assistant_node" in kinds


def test_private_turn_is_not_relayed(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        mate_headers, _ = join_workspace(client, owner_headers, wid)

        priv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "secret", "visibility": "private"},
            headers=owner_headers,
        ).json()

        with client.websocket_connect(
            f"/ws/workspaces/{wid}?token={_token(mate_headers)}"
        ) as ws_mate:
            ws_mate.receive_text()  # own presence frame

            client.post(
                f"/conversations/{priv['branch_id']}/messages",
                json={"prompt": "my private note"},
                headers=owner_headers,
            )
            # Nothing may arrive. Prove it with a ping round-trip: the pong is
            # the *next* frame, so no run_event slipped in ahead of it.
            ws_mate.send_text("ping")
            frame = json.loads(ws_mate.receive_text())
            assert frame["kind"] == "pong"


def test_conversation_created_broadcast(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        mate_headers, _ = join_workspace(client, owner_headers, wid)

        with client.websocket_connect(
            f"/ws/workspaces/{wid}?token={_token(mate_headers)}"
        ) as ws_mate:
            ws_mate.receive_text()  # own presence frame
            client.post(
                "/conversations",
                json={"workspace_id": wid, "title": "fresh"},
                headers=owner_headers,
            )
            frame = json.loads(ws_mate.receive_text())
            assert frame["kind"] == "conversation.created"
            assert frame["title"] == "fresh"


def test_drafting_signal_reaches_the_room(make_workspace, join_workspace):
    """A question being composed in a shared thread shows up in the roster.

    Ids only: the frame carries which conversation is being drafted in and
    which thread it overlaps, never the draft text.
    """
    with TestClient(app) as client:
        owner_headers, owner_id, wid = make_workspace(client)
        mate_headers, _ = join_workspace(client, owner_headers, wid)

        here = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "chunking", "visibility": "shared"},
            headers=owner_headers,
        ).json()
        prior = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "retrieval", "visibility": "shared"},
            headers=owner_headers,
        ).json()

        with client.websocket_connect(
            f"/ws/workspaces/{wid}?token={_token(mate_headers)}"
        ) as ws_mate:
            ws_mate.receive_text()  # own presence frame
            with client.websocket_connect(
                f"/ws/workspaces/{wid}?token={_token(owner_headers)}"
            ) as ws_owner:
                ws_mate.receive_text()  # roster grew to two

                ws_owner.send_text(json.dumps({
                    "kind": "drafting",
                    "conversation_id": here["conversation_id"],
                    "active": True,
                    "match_conversation_id": prior["conversation_id"],
                }))
                frame = json.loads(ws_mate.receive_text())
                assert frame["kind"] == "presence"
                drafter = next(u for u in frame["users"] if u["user_id"] == owner_id)
                assert drafter["drafting_conversation"] == here["conversation_id"]
                assert drafter["drafting_match"] == prior["conversation_id"]
                assert "draft" not in json.dumps(frame).lower().replace("drafting", "")

                # Clearing the composer takes it back out of the roster.
                ws_owner.send_text(json.dumps({
                    "kind": "drafting", "conversation_id": None, "active": False,
                }))
                cleared = json.loads(ws_mate.receive_text())
                drafter = next(u for u in cleared["users"] if u["user_id"] == owner_id)
                assert drafter["drafting_conversation"] is None


def test_drafting_in_a_private_thread_is_never_broadcast(make_workspace, join_workspace):
    """The client may claim anything; the server checks visibility itself."""
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        mate_headers, _ = join_workspace(client, owner_headers, wid)

        priv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "secret", "visibility": "private"},
            headers=owner_headers,
        ).json()

        with client.websocket_connect(
            f"/ws/workspaces/{wid}?token={_token(mate_headers)}"
        ) as ws_mate:
            ws_mate.receive_text()  # own presence frame
            with client.websocket_connect(
                f"/ws/workspaces/{wid}?token={_token(owner_headers)}"
            ) as ws_owner:
                ws_mate.receive_text()  # roster grew to two

                ws_owner.send_text(json.dumps({
                    "kind": "drafting",
                    "conversation_id": priv["conversation_id"],
                    "active": True,
                    "match_conversation_id": None,
                }))
                # Nothing may arrive: the pong is the next frame, so no presence
                # update carrying the private thread slipped in ahead of it.
                ws_mate.send_text("ping")
                frame = json.loads(ws_mate.receive_text())
                assert frame["kind"] == "pong"
