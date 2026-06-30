"""HTTP-level tests for the prompt library + insert path through the real app.

Drives the FastAPI app with the default stub provider via TestClient, proving the
save -> list/search -> get surface and the `from-prompt` insert (a saved prompt
running as a chat turn, streamed as SSE).
"""
import json

from starlette.testclient import TestClient

from api.main import app


def test_prompt_crud_and_search():
    with TestClient(app) as client:
        created = client.post(
            "/workspaces/wsX/prompts",
            json={"title": "Triage", "body": "find root cause", "tags": ["Debug"]},
        ).json()
        assert created["tags"] == ["debug"]
        pid = created["id"]

        got = client.get(f"/prompts/{pid}").json()
        assert got["body"] == "find root cause"

        listed = client.get("/workspaces/wsX/prompts", params={"tag": "debug"}).json()
        assert any(p["id"] == pid for p in listed["prompts"])

        searched = client.get("/workspaces/wsX/prompts", params={"q": "root cause"}).json()
        assert any(p["id"] == pid for p in searched["prompts"])

        assert client.get("/prompts/missing").status_code == 404


def test_insert_prompt_runs_as_conversation_turn():
    with TestClient(app) as client:
        pid = client.post(
            "/workspaces/wsY/prompts",
            json={"title": "Q", "body": "What are the tradeoffs?"},
        ).json()["id"]
        branch_id = client.post("/conversations", json={"title": "t"}).json()["branch_id"]

        resp = client.post(
            f"/conversations/{branch_id}/messages/from-prompt",
            json={"prompt_id": pid},
        )
        assert resp.status_code == 200
        payloads = [
            line[len("data: ") :]
            for line in resp.text.splitlines()
            if line.startswith("data: ")
        ]
        assert payloads[-1] == "[DONE]"
        user_nodes = [
            json.loads(p) for p in payloads if p != "[DONE]" and json.loads(p)["kind"] == "user_node"
        ]
        assert user_nodes[0]["node"]["content"] == "What are the tradeoffs?"


def test_insert_missing_prompt_is_404():
    with TestClient(app) as client:
        branch_id = client.post("/conversations", json={"title": "t"}).json()["branch_id"]
        resp = client.post(
            f"/conversations/{branch_id}/messages/from-prompt",
            json={"prompt_id": "nope"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"
