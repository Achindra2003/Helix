"""Deep-run persistence: every completed run leaves an inspectable record.

HTTP tests drive the real app with a fake graph (same harness as the router
tests); the recorder's segment semantics (paused segments persist nothing) are
unit-tested directly.
"""
import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import api.conversation.router as router_mod
from api.conversation.events import Complete, Step, Waiting
from api.conversation.run_log import DeepRunRecorder
from api.conversation.store import InMemoryStore
from api.main import app


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _create_conv(client, headers, workspace_id, **overrides):
    payload = {"workspace_id": workspace_id, "title": "demo", **overrides}
    resp = client.post("/conversations", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


class _Chunk:
    def __init__(self, content):
        self.content = content


class _FakeGraph:
    async def astream(self, inputs, config, stream_mode):
        yield (
            "updates",
            {
                "synthesize": {
                    "depth": 2,
                    "energy": 70.0,
                    "synthesis": "Decisive answer.",
                    "stability": 0.93,
                    "confidence": 0.9,
                    "confidence_reported": True,
                    "stop_reason": "converged",
                }
            },
        )
        yield ("messages", (_Chunk("Decisive answer."), {"langgraph_node": "surface"}))
        yield ("updates", {"surface": {"surfaced_insight": "Decisive answer."}})

    async def aget_state(self, config):
        return SimpleNamespace(next=())


def _run_deep(client, headers, branch_id, prompt="hard question"):
    resp = client.post(
        f"/conversations/{branch_id}/deep", json={"prompt": prompt}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp


def test_completed_run_is_persisted_and_readable(monkeypatch, make_workspace):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(
        router_mod,
        "build_ouroboros_graph",
        lambda **kw: (_FakeGraph(), {}, lambda seed: {"seed": seed}, lambda: 777),
    )
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        created = _create_conv(client, headers, wid, title="deep")
        conv_id, branch_id = created["conversation_id"], created["branch_id"]
        _run_deep(client, headers, branch_id)

        listing = client.get(f"/conversations/{conv_id}/deep/runs", headers=headers)
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert len(items) == 1
        summary = items[0]
        assert summary["question"] == "hard question"
        assert summary["status"] == "done"
        assert summary["stop_reason"] == "converged"
        assert summary["stability"] == 0.93
        assert summary["tokens_used"] == 777

        record = client.get(
            f"/conversations/deep/runs/{summary['id']}/record", headers=headers
        ).json()
        assert record["answer"] == "Decisive answer."
        assert record["author_id"] == uid
        trace = record["trace"]
        assert trace["stability_history"] == [0.93]
        assert any(s["node"] == "synthesize" for s in trace["steps"])
        # Step excerpts are compact diagnostics, not archival dumps.
        assert all(len(s.get("synthesis", "")) <= 300 for s in trace["steps"])


def test_run_records_are_tenancy_gated(monkeypatch, make_workspace, make_user):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(
        router_mod,
        "build_ouroboros_graph",
        lambda **kw: (_FakeGraph(), {}, lambda seed: {"seed": seed}, lambda: 1),
    )
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        created = _create_conv(client, headers, wid, title="deep")
        conv_id, branch_id = created["conversation_id"], created["branch_id"]
        _run_deep(client, headers, branch_id)
        run_id = client.get(
            f"/conversations/{conv_id}/deep/runs", headers=headers
        ).json()["items"][0]["id"]

        outsider, _ = make_user(client)
        assert (
            client.get(f"/conversations/{conv_id}/deep/runs", headers=outsider).status_code
            == 404
        )
        assert (
            client.get(
                f"/conversations/deep/runs/{run_id}/record", headers=outsider
            ).status_code
            == 404
        )


# --- recorder segment semantics -------------------------------------------------


class _FakeSessionFactory:
    """Records what would be committed, without a database."""

    def __init__(self):
        self.rows = []

    def __call__(self):
        factory = self

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def add(self, row):
                factory.rows.append(row)

            async def commit(self):
                pass

        return _Session()


def _recorder(sf):
    return DeepRunRecorder(
        run_id="r1",
        workspace_id="w1",
        conversation_id="c1",
        branch_id="b1",
        author_id="u1",
        session_factory=sf,
    )


async def test_paused_segment_persists_nothing_then_final_segment_persists_once():
    sf = _FakeSessionFactory()
    rec = _recorder(sf)
    rec.observe(Step(idx=1, node="synthesize", depth=1, energy=50.0, payload={"stability": 0.4}))
    rec.observe(Waiting())
    await rec.flush()  # segment ended on a pause: no terminal status
    assert sf.rows == []

    rec.note_steer("focus on cost")
    rec.observe(Step(idx=2, node="synthesize", depth=2, energy=45.0, payload={"stability": 0.95}))
    rec.observe(Complete(stop_reason="converged", status="done"))
    await rec.flush()
    await rec.flush()  # idempotent — a second flush must not double-write
    assert len(sf.rows) == 1
    row = sf.rows[0]
    assert row.status == "done"
    assert row.depth == 2
    trace = json.loads(row.trace)
    assert trace["steers"] == ["focus on cost"]
    assert trace["stability_history"] == [0.4, 0.95]
