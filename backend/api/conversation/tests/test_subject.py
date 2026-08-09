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


# --- the records the subject has to reach ---------------------------------------
# It used to reach exactly one audience: the model's context. That is the one
# reader who does not need to remember which change this was, because it is told
# again every turn. The people who need it are the ones reading the record
# afterwards — so these pin the artifacts a team actually leaves with.


def test_the_decision_report_names_the_change(make_workspace):
    """An ADR that cannot name its pull request decays into folklore: a reader
    six months later cannot tell whether the decision survived contact."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, branch_id = created["conversation_id"], created["branch_id"]

        client.post(
            f"/conversations/{cid}/subject",
            json={"subject": "PR #482 — cache the workspace index"},
            headers=headers,
        )
        client.post(
            f"/conversations/branches/{branch_id}/resolve",
            json={"status": "adopted", "resolution": "Cache it; the index is cold."},
            headers=headers,
        )

        report = client.get(f"/workspaces/{wid}/export?format=md", headers=headers)
        assert report.status_code == 200, report.text
        assert "PR #482" in report.text
        assert "Cache it; the index is cold." in report.text

        as_json = client.get(f"/workspaces/{wid}/export?format=json", headers=headers).json()
        assert as_json["threads"][0]["subject"] == "PR #482 — cache the workspace index"


def test_a_thread_with_no_subject_says_nothing_about_one(make_workspace):
    """The line is absent, not empty. A report full of "About: " reads as a
    broken template."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        client.post(
            f"/conversations/branches/{created['branch_id']}/resolve",
            json={"status": "adopted", "resolution": "Ship it."},
            headers=headers,
        )
        report = client.get(f"/workspaces/{wid}/export?format=md", headers=headers).text
        assert "About:" not in report


def test_both_conversation_exports_name_the_change(make_workspace):
    """`/export` is two documents behind one route: with `branch` it is the fair
    copy of one path, without it the whole thread as a decision report. Both get
    handed to someone who was not there, so both have to say which change."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(
            f"/conversations/{cid}/subject",
            json={"subject": "PR #482 — cache the workspace index"},
            headers=headers,
        )

        transcript = client.get(
            f"/conversations/{cid}/export?format=md&branch={branch_id}", headers=headers
        )
        assert transcript.status_code == 200, transcript.text
        assert "PR #482" in transcript.text

        report = client.get(f"/conversations/{cid}/export?format=md", headers=headers)
        assert report.status_code == 200, report.text
        assert "PR #482" in report.text


def test_a_run_records_what_it_was_reasoning_about(monkeypatch, make_workspace):
    """A Review run's value is that its verdict traces back to the change it
    judged. Without this the archive holds a review of "this patch" and no way
    to tell which patch."""
    from types import SimpleNamespace

    class _FakeGraph:
        async def astream(self, inputs, config, stream_mode):
            yield ("updates", {"synthesize": {"depth": 1, "synthesis": "Fine.",
                                              "stop_reason": "converged"}})
            yield ("updates", {"surface": {"surfaced_insight": "Fine."}})

        async def aget_state(self, config):
            return SimpleNamespace(next=())

    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(
        router_mod, "build_ouroboros_graph",
        lambda **kw: (_FakeGraph(), {}, lambda seed: {"seed": seed}, lambda: 1),
    )
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _conv(client, headers, wid)
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(
            f"/conversations/{cid}/subject",
            json={"subject": "PR #482 — cache the workspace index"},
            headers=headers,
        )
        client.post(
            f"/conversations/{branch_id}/deep",
            json={"prompt": "review it", "mode": "review"},
            headers=headers,
        )

        runs = client.get(f"/conversations/{cid}/deep/runs", headers=headers).json()["items"]
        record = client.get(
            f"/conversations/deep/runs/{runs[0]['id']}/record", headers=headers
        ).json()
        assert record["provenance"]["subject"] == "PR #482 — cache the workspace index"
