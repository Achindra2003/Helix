"""Backing a branch — the move that answers forking.

Forking was cheap and converging had no primitive at all, so a thread could
accumulate four live alternatives nobody had ruled out. These cover the signal
that precedes a verdict: approval voting, one voice per member per branch,
deciding nothing on its own.
"""
import pytest
from starlette.testclient import TestClient

import api.conversation.router as router_mod
from api.conversation.store import InMemoryStore
from api.main import app


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _conv(client, headers, wid, title="Which retriever?"):
    resp = client.post(
        "/conversations", json={"workspace_id": wid, "title": title}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _fork(client, headers, cid, branch_id, name):
    """A second exploration under the same question."""
    hist = client.post(
        f"/conversations/{branch_id}/messages", json={"prompt": "go"}, headers=headers
    )
    assert hist.status_code == 200, hist.text
    nodes = client.get(
        f"/conversations/branches/{branch_id}/history", headers=headers
    ).json()["nodes"]
    resp = client.post(
        f"/conversations/{cid}/fork",
        json={"from_node_id": nodes[-1]["id"], "name": name},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["branch_id"]


def test_backing_toggles_and_is_counted(make_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        branch_id = _conv(client, headers, wid)["branch_id"]

        first = client.post(
            f"/conversations/branches/{branch_id}/vote", headers=headers
        ).json()
        assert first["backing"] is True
        assert first["votes"] == [uid]

        # Clicking twice leaves no trace — which is what makes a vote safe to
        # cast on a hunch.
        second = client.post(
            f"/conversations/branches/{branch_id}/vote", headers=headers
        ).json()
        assert second["backing"] is False
        assert second["votes"] == []


def test_one_member_one_voice(make_workspace):
    """Repeated backing cannot inflate a tally — the unique constraint,
    exercised through the route."""
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, branch_id = created["conversation_id"], created["branch_id"]

        # Odd number of toggles leaves the member backing it, exactly once.
        for _ in range(3):
            client.post(f"/conversations/branches/{branch_id}/vote", headers=headers)

        tree = client.get(f"/conversations/{cid}/branches", headers=headers).json()
        branch = next(b for b in tree["items"] if b["id"] == branch_id)
        assert branch["votes"] == [uid]


def test_backing_is_approval_not_choice(make_workspace):
    """Backing one exploration says nothing about its siblings. The useful
    signal in a design argument is "either of these two works"."""
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, main = created["conversation_id"], created["branch_id"]
        alt = _fork(client, headers, cid, main, "alt")

        client.post(f"/conversations/branches/{main}/vote", headers=headers)
        client.post(f"/conversations/branches/{alt}/vote", headers=headers)

        tree = client.get(f"/conversations/{cid}/branches", headers=headers).json()
        by_id = {b["id"]: b for b in tree["items"]}
        assert by_id[main]["votes"] == [uid]
        assert by_id[alt]["votes"] == [uid], "backing one must not clear the other"


def test_two_members_accumulate(make_workspace, join_workspace):
    with TestClient(app) as client:
        headers, owner, wid = make_workspace(client)
        mate_headers, mate = join_workspace(client, headers, wid, role="collaborator")
        branch_id = _conv(client, headers, wid)["branch_id"]

        client.post(f"/conversations/branches/{branch_id}/vote", headers=headers)
        result = client.post(
            f"/conversations/branches/{branch_id}/vote", headers=mate_headers
        ).json()
        assert sorted(result["votes"]) == sorted([owner, mate])


def test_a_vote_is_not_a_verdict(make_workspace):
    """The tally must not resolve anything. A branch everyone backed is still
    `open` until a member writes down why — which is the whole point: a
    decision the team can defend is one somebody took responsibility for."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, branch_id = created["conversation_id"], created["branch_id"]

        client.post(f"/conversations/branches/{branch_id}/vote", headers=headers)

        tree = client.get(f"/conversations/{cid}/branches", headers=headers).json()
        branch = next(b for b in tree["items"] if b["id"] == branch_id)
        assert branch["status"] == "open"
        assert branch["resolution"] == ""


def test_observers_cannot_back_a_branch(make_workspace, join_workspace):
    """Same bar as forking: whoever may explore may weigh in. An observer is
    reading the room, not in it."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        obs_headers, _ = join_workspace(client, headers, wid, role="observer")
        branch_id = _conv(client, headers, wid)["branch_id"]

        resp = client.post(
            f"/conversations/branches/{branch_id}/vote", headers=obs_headers
        )
        assert resp.status_code == 403


def test_non_members_cannot_see_or_back(make_workspace, make_user):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _conv(client, headers, wid)["branch_id"]
        outsider = make_user(client)[0]

        resp = client.post(
            f"/conversations/branches/{branch_id}/vote", headers=outsider
        )
        # 404, not 403 — a non-member must not be able to probe what exists.
        assert resp.status_code == 404
