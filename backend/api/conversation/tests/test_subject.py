"""What "this change" refers to.

A dev team discusses "this change" for forty turns and never says the number.
Fine between people, useless to an agent: with a GitHub tool allowlisted it had
everything it needed to read the pull request except which pull request.
"""
import pytest
from starlette.testclient import TestClient

import api.conversation.router as router_mod
from api.conversation.context import build_messages
from api.conversation.events import Node
from api.conversation.store import InMemoryStore
from api.main import app


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _conv(client, headers, wid):
    resp = client.post(
        "/conversations", json={"workspace_id": wid, "title": "the cache change"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_the_subject_reaches_the_model_as_context():
    """Stated as fact, not as an instruction: it is context, and the prompt
    layer's whole discipline is that quoted material never gives orders."""
    history = [Node(id="1", branch_id="b", parent_id=None, seq=1, role="user",
                    content="does this match the spec?")]
    messages = build_messages(history, subject="https://github.com/acme/api/pull/482")

    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "https://github.com/acme/api/pull/482" in system
    assert "This thread is about" in system


def test_no_subject_adds_nothing():
    """Threads that are about nothing in particular must not pay for the
    feature with a line of context."""
    history = [Node(id="1", branch_id="b", parent_id=None, seq=1, role="user", content="hi")]
    plain = build_messages(history)
    assert not any("This thread is about" in m["content"] for m in plain)


def test_setting_and_clearing_a_subject(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        cid = _conv(client, headers, wid)["conversation_id"]

        resp = client.post(
            f"/conversations/{cid}/subject",
            json={"subject": "https://github.com/acme/api/pull/482"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["subject"] == "https://github.com/acme/api/pull/482"

        # A thread can stop being about a particular change.
        cleared = client.post(
            f"/conversations/{cid}/subject", json={"subject": ""}, headers=headers
        )
        assert cleared.json()["subject"] == ""


def test_observers_cannot_set_a_subject(make_workspace, join_workspace):
    """It changes what every future agent run is told, which is a write."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        obs_headers, _ = join_workspace(client, headers, wid, role="observer")
        cid = _conv(client, headers, wid)["conversation_id"]

        resp = client.post(
            f"/conversations/{cid}/subject",
            json={"subject": "https://example.com/pr/1"},
            headers=obs_headers,
        )
        assert resp.status_code == 403


def test_non_members_get_404(make_workspace, make_user):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        cid = _conv(client, headers, wid)["conversation_id"]
        outsider = make_user(client)[0]

        resp = client.post(
            f"/conversations/{cid}/subject", json={"subject": "x"}, headers=outsider
        )
        assert resp.status_code == 404
