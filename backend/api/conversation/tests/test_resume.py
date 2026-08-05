"""Paused runs across a restart (conversation/resume.py).

The failure this closes: a guided deep run pauses for human guidance, someone
goes to lunch, the server is redeployed, and "steer" answers 404 — a 404 that
was not true, because the run had neither finished nor expired. It had been
kept in a dict.

A restart is simulated by clearing `RunManager._handles`, which is exactly what
a new process starts with. Everything else is real: the row is written by the
driver, read back by the rehydrator, and the graph is rebuilt on the same
`thread_id`.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from api.conversation import router as router_mod
from api.conversation import deep_reasoning as deep_mod
from api.main import app

from .test_router import _create_conv, _parse_sse


class _Chunk:
    def __init__(self, content):
        self.content = content


class _PausingGraph:
    """Streams a token, pauses at the steer checkpoint, then finishes.

    The token before the pause is the point: the assistant node is written once
    from every segment's tokens joined, so a run rebuilt without its earlier
    text would publish a reply missing its first half.
    """

    def __init__(self):
        self.updates = []
        self.resumed = False

    async def astream(self, inputs, config, stream_mode):
        if inputs is not None:
            yield ("messages", (_Chunk("Before the restart. "), {"langgraph_node": "surface"}))
            yield ("updates", {"think": {"depth": 1, "energy": 70.0, "thought": "draft"}})
        else:
            yield ("messages", (_Chunk("After it."), {"langgraph_node": "surface"}))
            yield ("updates", {"surface": {"surfaced_insight": "done", "stop_reason": "converged"}})

    async def aget_state(self, config):
        return SimpleNamespace(next=() if self.resumed else ("steer",))

    async def aupdate_state(self, config, values):
        self.resumed = True
        self.updates.append(values)


@pytest.fixture
def pausing_graph(monkeypatch):
    """Patch both build sites.

    The router imports `build_ouroboros_graph` at module scope; `resume`
    imports it inside the function to avoid an import cycle, so it resolves
    from `deep_reasoning` at call time. Patching one and not the other tests
    half the path and passes.
    """
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    threads: list[str] = []

    def factory(**kw):
        threads.append(kw.get("thread_id", ""))
        return (_PausingGraph(), {}, lambda seed: {"seed": seed}, lambda: 42)

    monkeypatch.setattr(router_mod, "build_ouroboros_graph", factory)
    monkeypatch.setattr(deep_mod, "build_ouroboros_graph", factory)
    return threads



def _start_guided(client, headers, wid):
    branch_id = _create_conv(client, headers, wid, title="guided")["branch_id"]
    resp = client.post(
        f"/conversations/{branch_id}/deep",
        json={"prompt": "hard question", "steerable": True},
        headers=headers,
    )
    assert resp.status_code == 200
    events = [json.loads(p) for p in _parse_sse(resp.text) if p != "[DONE]"]
    assert "waiting" in [e["kind"] for e in events], events
    return branch_id, events[0]["run_id"]


def test_a_paused_run_survives_a_restart(pausing_graph, make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id, run_id = _start_guided(client, headers, wid)

        # --- the restart -----------------------------------------------------
        # Clearing the handles is exactly what a new process starts with. That
        # the steer below works at all is the proof the row was written.
        router_mod._runs._handles.clear()

        resumed = client.post(
            f"/conversations/deep/runs/{run_id}/steer",
            json={"guidance": "keep going"},
            headers=headers,
        )
        assert resumed.status_code == 200, resumed.text
        kinds = [json.loads(p)["kind"] for p in _parse_sse(resumed.text) if p != "[DONE]"]
        assert "assistant_node" in kinds

        # The graph was rebuilt on the *same* thread_id — otherwise it would
        # have resumed a checkpoint that does not exist.
        assert len(pausing_graph) == 2
        assert pausing_graph[0] == pausing_graph[1]

        hist = client.get(
            f"/conversations/branches/{branch_id}/history", headers=headers
        ).json()["nodes"]
        assert [n["role"] for n in hist] == ["user", "assistant"]
        # Both halves. This is what `ResumableRun.restore(parts=...)` buys.
        assert hist[-1]["content"] == "Before the restart. After it."


def test_a_run_that_finished_leaves_nothing_to_resume(pausing_graph, make_workspace):
    """A row means "still owed a human answer". Once the run completes, an
    offer to resume it would rebuild a graph with nothing left to do."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        _, run_id = _start_guided(client, headers, wid)
        client.post(
            f"/conversations/deep/runs/{run_id}/steer",
            json={"guidance": "finish"}, headers=headers,
        )

        router_mod._runs._handles.clear()
        gone = client.post(
            f"/conversations/deep/runs/{run_id}/steer",
            json={"guidance": "again"}, headers=headers,
        )
        assert gone.status_code == 404


def test_killing_a_paused_run_clears_its_row(pausing_graph, make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        _, run_id = _start_guided(client, headers, wid)
        assert client.post(
            f"/conversations/deep/runs/{run_id}/kill", headers=headers
        ).status_code == 200

        router_mod._runs._handles.clear()
        gone = client.post(
            f"/conversations/deep/runs/{run_id}/steer",
            json={"guidance": "zombie"}, headers=headers,
        )
        assert gone.status_code == 404


def test_an_unknown_run_is_still_a_404(make_workspace):
    with TestClient(app) as client:
        headers, _, _ = make_workspace(client)
        r = client.post(
            "/conversations/deep/runs/does-not-exist/steer",
            json={"guidance": "hello"}, headers=headers,
        )
        assert r.status_code == 404
