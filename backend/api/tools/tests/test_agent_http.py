"""HTTP wiring for FR-14: the agent run endpoints, the approval flow, and the
owner-managed tool allowlist settings.

Same recipe as the deep-run router tests: real FastAPI app, real auth/RBAC in
the hermetic DB, in-memory conversation store, and `build_agent_graph`
monkeypatched to a fake — the graph itself is proven in test_agent_graph.py;
here we prove the HTTP surface around it.
"""
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from starlette.testclient import TestClient

import api.conversation.router as router_mod
from api.conversation.store import InMemoryStore
from api.main import app


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    monkeypatch.setattr(router_mod, "_store", InMemoryStore())


def _parse_sse(body: str) -> list[str]:
    return [line[len("data: ") :] for line in body.splitlines() if line.startswith("data: ")]


def _events(body: str) -> list[dict]:
    return [json.loads(p) for p in _parse_sse(body) if p != "[DONE]"]


def _create_conv(client, headers, workspace_id):
    resp = client.post(
        "/conversations", json={"workspace_id": workspace_id, "title": "demo"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class _FakeAgentGraph:
    """One safe tool round, then the answer. `pause_at_gate=True` ends the
    first drive paused for approval; the second drive finishes."""

    def __init__(self, pause_at_gate=False):
        self._pause = pause_at_gate
        self._drives = 0
        self.decisions = []

    async def astream(self, inputs, config, stream_mode):
        self._drives += 1
        if self._drives == 1:
            yield (
                "updates",
                {"agent": {"messages": [AIMessage(content="", tool_calls=[
                    {"name": "web_search" if self._pause else "search_knowledge_base",
                     "args": {"query": "q"}, "id": "c1", "type": "tool_call"}
                ])]}},
            )
            if self._pause:
                return
            yield (
                "updates",
                {"tools": {"messages": [ToolMessage(content="found it", tool_call_id="c1", name="search_knowledge_base")]}},
            )
            yield ("updates", {"agent": {"messages": [AIMessage(content="Answer: found it.")]}})
        else:
            yield (
                "updates",
                {"tools": {"messages": [ToolMessage(content="web says hi", tool_call_id="c1", name="web_search")]}},
            )
            yield ("updates", {"agent": {"messages": [AIMessage(content="Approved answer.")]}})

    async def aget_state(self, config):
        pending = ("gate",) if (self._pause and self._drives == 1) else ()
        return SimpleNamespace(next=pending)

    async def aupdate_state(self, config, values):
        self.decisions.append(values)


def _patch_graph(monkeypatch, graph):
    captured = {}

    def fake_build(**kw):
        captured.update(kw)
        return graph, {}, lambda msgs: {"messages": msgs}

    monkeypatch.setattr(router_mod, "build_agent_graph", fake_build)
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "test-key")
    return captured


# --- the run ------------------------------------------------------------------


def test_agent_turn_streams_tool_loop_and_persists(monkeypatch, make_workspace):
    captured = _patch_graph(monkeypatch, _FakeAgentGraph())
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]

        resp = client.post(
            f"/conversations/{branch_id}/agent", json={"prompt": "find it"},
            headers=headers,
        )
        assert resp.status_code == 200
        events = _events(resp.text)
        kinds = [e["kind"] for e in events]
        assert kinds[0] == "agent_run" and events[0]["run_id"]
        assert kinds[1] == "user_node"
        assert "tool_call" in kinds and "tool_result" in kinds
        assert kinds.index("tool_call") < kinds.index("tool_result")
        assert kinds[-1] == "assistant_node"
        assert events[-1]["node"]["content"] == "Answer: found it."

        call = next(e for e in events if e["kind"] == "tool_call")
        assert call["name"] == "search_knowledge_base"
        assert call["arguments"] == {"query": "q"}

        # Default allowlist wiring: only the two workspace-internal tools are
        # bound (web_search has no key AND isn't allowed by default).
        assert [t.name for t in captured["tools"]] == [
            "search_knowledge_base", "search_conversations",
        ]

        # The run left a durable record stamped as an agent run.
        record = client.get(
            f"/conversations/deep/runs/{events[0]['run_id']}/record", headers=headers
        )
        assert record.status_code == 200
        assert record.json()["provenance"]["kind"] == "agent"
        assert record.json()["answer"] == "Answer: found it."


def test_agent_without_groq_key_is_503(monkeypatch, make_workspace):
    monkeypatch.setattr(router_mod.settings, "groq_api_key", "")
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        resp = client.post(
            f"/conversations/{branch_id}/agent", json={"prompt": "x"}, headers=headers
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "agent_unavailable"


def test_agent_requires_collaborator(monkeypatch, make_workspace, join_workspace):
    _patch_graph(monkeypatch, _FakeAgentGraph())
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, owner_headers, wid)["branch_id"]
        observer_headers, _ = join_workspace(client, owner_headers, wid, role="observer")
        resp = client.post(
            f"/conversations/{branch_id}/agent", json={"prompt": "x"},
            headers=observer_headers,
        )
        assert resp.status_code == 403


# --- approval flow --------------------------------------------------------------


def test_sensitive_pause_then_approve_resumes_and_persists(monkeypatch, make_workspace):
    graph = _FakeAgentGraph(pause_at_gate=True)
    _patch_graph(monkeypatch, graph)
    # web_search must be available (key) AND owner-allowed to be bound at all.
    monkeypatch.setattr(router_mod.settings, "tavily_api_key", "tvly-test")
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        assert client.put(
            f"/api/workspaces/{wid}/settings/tools",
            json={"allowed": ["search_knowledge_base", "search_conversations", "web_search"]},
            headers=headers,
        ).status_code == 200

        first = client.post(
            f"/conversations/{branch_id}/agent", json={"prompt": "search the web"},
            headers=headers,
        )
        events = _events(first.text)
        kinds = [e["kind"] for e in events]
        run_id = events[0]["run_id"]
        # Paused: the stream ends on waiting(approval), nothing persisted yet.
        assert kinds[-1] == "waiting"
        assert events[-1]["reason"] == "approval"
        assert "assistant_node" not in kinds
        call = next(e for e in events if e["kind"] == "tool_call")
        assert call["sensitive"] is True

        status = client.get(f"/conversations/deep/runs/{run_id}/status", headers=headers)
        assert status.json()["status"] == "paused"

        second = client.post(
            f"/conversations/agent/runs/{run_id}/approve",
            json={"approved": True}, headers=headers,
        )
        assert second.status_code == 200
        cont = _events(second.text)
        assert graph.decisions == [{"decision": "approve"}]
        assert [e["kind"] for e in cont][-1] == "assistant_node"
        assert cont[-1]["node"]["content"] == "Approved answer."


def test_approve_when_not_paused_is_409_and_unknown_is_404(monkeypatch, make_workspace):
    _patch_graph(monkeypatch, _FakeAgentGraph())
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        run_id = _events(
            client.post(
                f"/conversations/{branch_id}/agent", json={"prompt": "x"}, headers=headers
            ).text
        )[0]["run_id"]

        resp = client.post(
            f"/conversations/agent/runs/{run_id}/approve",
            json={"approved": True}, headers=headers,
        )
        assert resp.status_code == 409
        assert (
            client.post(
                "/conversations/agent/runs/nope/approve",
                json={"approved": True}, headers=headers,
            ).status_code
            == 404
        )


def test_approval_is_membership_gated(monkeypatch, make_workspace, make_user):
    graph = _FakeAgentGraph(pause_at_gate=True)
    _patch_graph(monkeypatch, graph)
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        run_id = _events(
            client.post(
                f"/conversations/{branch_id}/agent", json={"prompt": "x"}, headers=headers
            ).text
        )[0]["run_id"]

        outsider, _ = make_user(client)
        resp = client.post(
            f"/conversations/agent/runs/{run_id}/approve",
            json={"approved": True}, headers=outsider,
        )
        assert resp.status_code == 404  # not even existence


# --- allowlist settings ---------------------------------------------------------


def test_tool_settings_default_catalog_shape(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        resp = client.get(f"/api/workspaces/{wid}/settings/tools", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] == ["search_knowledge_base", "search_conversations"]
        by_name = {i["name"]: i for i in data["items"]}
        assert by_name["web_search"]["sensitive"] is True
        assert by_name["web_search"]["available"] is False  # no Tavily key
        assert by_name["web_search"]["allowed"] is False
        assert by_name["search_knowledge_base"]["allowed"] is True


def test_owner_sets_allowlist_and_it_binds_the_agent(monkeypatch, make_workspace):
    captured = _patch_graph(monkeypatch, _FakeAgentGraph())
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]

        put = client.put(
            f"/api/workspaces/{wid}/settings/tools",
            json={"allowed": ["search_knowledge_base"]}, headers=headers,
        )
        assert put.status_code == 200
        assert put.json()["allowed"] == ["search_knowledge_base"]

        client.post(
            f"/conversations/{branch_id}/agent", json={"prompt": "x"}, headers=headers
        )
        assert [t.name for t in captured["tools"]] == ["search_knowledge_base"]


def test_empty_allowlist_is_a_toolless_agent_not_the_default(monkeypatch, make_workspace):
    captured = _patch_graph(monkeypatch, _FakeAgentGraph())
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        client.put(
            f"/api/workspaces/{wid}/settings/tools", json={"allowed": []}, headers=headers
        )
        assert (
            client.get(f"/api/workspaces/{wid}/settings/tools", headers=headers).json()["allowed"]
            == []
        )
        client.post(
            f"/conversations/{branch_id}/agent", json={"prompt": "x"}, headers=headers
        )
        assert captured["tools"] == []


def test_allowlist_rejects_unknown_tools(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        resp = client.put(
            f"/api/workspaces/{wid}/settings/tools",
            json={"allowed": ["rm_rf_slash"]}, headers=headers,
        )
        assert resp.status_code == 400
        assert "rm_rf_slash" in resp.json()["error"]["message"]


def test_allowlist_is_owner_only_to_write_member_read(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        collab_headers, _ = join_workspace(client, owner_headers, wid)
        assert (
            client.get(f"/api/workspaces/{wid}/settings/tools", headers=collab_headers).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/workspaces/{wid}/settings/tools",
                json={"allowed": []}, headers=collab_headers,
            ).status_code
            == 403
        )


def test_allowlist_does_not_disturb_provider_settings(make_workspace):
    """Both live on the same WorkspaceSettings row — setting one must not
    clobber the other."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        client.put(
            f"/api/workspaces/{wid}/settings/provider",
            json={"provider": "groq", "api_key": "gsk_secret_key_123"},
            headers=headers,
        )
        client.put(
            f"/api/workspaces/{wid}/settings/tools",
            json={"allowed": ["search_conversations"]}, headers=headers,
        )
        prov = client.get(f"/api/workspaces/{wid}/settings/provider", headers=headers).json()
        assert prov["provider"] == "groq" and prov["api_key_masked"]
        tools = client.get(f"/api/workspaces/{wid}/settings/tools", headers=headers).json()
        assert tools["allowed"] == ["search_conversations"]
