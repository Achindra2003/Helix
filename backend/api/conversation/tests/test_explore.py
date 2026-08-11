"""Diverging cheaply — the counter-move to converging.

Helix could already converge: back a branch, adopt one with a written reason,
and the export names the alternative that lost. Diverging cost a dialog and a
naming decision *per branch*, so "let's try four things" was priced like "let's
commit to one" — and a brainstorm is mostly the first thing.

These cover the half that is not obvious: that a disposable exploration still
records what it was trying, that the fan-out is one act rather than four, and
that nothing about being cheap makes it exempt from the permission model.
"""
import pytest
from starlette.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _thread(client, headers, wid, **overrides):
    payload = {"workspace_id": wid, "title": "onboarding", **overrides}
    resp = client.post("/conversations", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _head(client, headers, branch_id):
    nodes = client.get(
        f"/conversations/branches/{branch_id}/history", headers=headers
    ).json()["nodes"]
    return nodes[-1]["id"] if nodes else None


ANGLES = ["a guided tour", "sample data on signup", "a concierge call"]


def _explore(client, headers, cid, node_id, angles=ANGLES):
    return client.post(
        f"/conversations/{cid}/explore",
        json={"from_node_id": node_id, "angles": angles},
        headers=headers,
    )


def test_one_action_makes_several_explorations(client, make_workspace):
    headers, _, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    client.post(
        f"/conversations/{conv['branch_id']}/messages",
        json={"prompt": "how should onboarding work?"},
        headers=headers,
    )
    node = _head(client, headers, conv["branch_id"])

    resp = _explore(client, headers, conv["conversation_id"], node)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 3

    tree = client.get(
        f"/conversations/{conv['conversation_id']}/branches", headers=headers
    ).json()["items"]
    assert len(tree) == 4  # main plus the three
    assert all(b["fork_node_id"] == node for b in tree if b["parent_branch_id"])


def test_a_disposable_exploration_still_says_what_it_tried(client, make_workspace):
    """The reason this is not just "fork, three times". An exploration with no
    recorded intent cannot carry a meaningful verdict later, and most of these
    are abandoned — the abandoned ones are half of why a decision holds up."""
    headers, _, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    node = conv["branch_id"] and _head(client, headers, conv["branch_id"])
    client.post(
        f"/conversations/{conv['branch_id']}/messages",
        json={"prompt": "how should onboarding work?"},
        headers=headers,
    )
    node = _head(client, headers, conv["branch_id"])

    items = _explore(client, headers, conv["conversation_id"], node).json()["items"]
    assert [b["intent"] for b in items] == ANGLES
    # And it is named from the angle rather than by asking twice.
    assert items[0]["name"] == "a-guided-tour"


def test_nobody_is_asked_to_name_anything(client, make_workspace):
    """A label nobody chose beats a dialog nobody wanted. Odd punctuation must
    not produce an empty or broken label."""
    headers, _, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    client.post(
        f"/conversations/{conv['branch_id']}/messages",
        json={"prompt": "q"}, headers=headers,
    )
    node = _head(client, headers, conv["branch_id"])

    items = _explore(
        client, headers, conv["conversation_id"], node,
        angles=["!!! ???", "ship it — fast, cheap"],
    ).json()["items"]
    assert items[0]["name"] == "exploration"  # nothing wordlike survived
    assert items[1]["name"] == "ship-it-fast"


def test_two_is_the_floor_and_six_the_ceiling(client, make_workspace):
    """One angle is a fork and should use the fork route; past six nobody reads
    the comparison, and an uncapped list lets one call make a hundred branches."""
    headers, _, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    client.post(
        f"/conversations/{conv['branch_id']}/messages",
        json={"prompt": "q"}, headers=headers,
    )
    node = _head(client, headers, conv["branch_id"])
    cid = conv["conversation_id"]

    assert _explore(client, headers, cid, node, angles=["only one"]).status_code == 422
    assert _explore(client, headers, cid, node, angles=[" ", ""]).status_code == 422
    assert _explore(
        client, headers, cid, node, angles=[f"angle {i}" for i in range(7)]
    ).status_code == 422


def test_an_unknown_node_is_a_404(client, make_workspace):
    headers, _, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    resp = _explore(client, headers, conv["conversation_id"], "no-such-node")
    assert resp.status_code == 404


def test_observers_cannot_explore(client, make_workspace, join_workspace):
    """Cheap is not the same as unprivileged: each branch is a write to the
    thread's lineage, which is exactly what an Observer may not do."""
    headers, _, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    client.post(
        f"/conversations/{conv['branch_id']}/messages",
        json={"prompt": "q"}, headers=headers,
    )
    node = _head(client, headers, conv["branch_id"])
    obs_headers, _ = join_workspace(client, headers, wid, role="observer")

    resp = _explore(client, obs_headers, conv["conversation_id"], node)
    assert resp.status_code == 403


def test_a_non_member_cannot_probe_for_threads(client, make_workspace, make_user):
    headers, _, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    outsider = make_user(client)[0]
    resp = _explore(client, outsider, conv["conversation_id"], "whatever")
    assert resp.status_code == 404


def test_the_explorations_can_then_be_converged(client, make_workspace):
    """The whole point: diverge cheaply, then use the machinery that already
    existed. Backing and adopting must work on a branch nobody named."""
    headers, uid, wid = make_workspace(client)
    conv = _thread(client, headers, wid)
    client.post(
        f"/conversations/{conv['branch_id']}/messages",
        json={"prompt": "q"}, headers=headers,
    )
    node = _head(client, headers, conv["branch_id"])
    items = _explore(client, headers, conv["conversation_id"], node).json()["items"]
    winner = items[1]["branch_id"]

    assert client.post(
        f"/conversations/branches/{winner}/vote", headers=headers
    ).json()["votes"] == [uid]
    assert client.post(
        f"/conversations/branches/{winner}/resolve",
        json={"status": "adopted", "resolution": "Fastest path to value."},
        headers=headers,
    ).status_code == 200

    report = client.get(f"/workspaces/{wid}/export?format=md", headers=headers).text
    assert "Fastest path to value." in report
    assert "sample data on signup" in report  # the angle survived as the intent
