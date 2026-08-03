"""HTTP-level tests for the prompt library + insert path through the real app.

Drives the FastAPI app with the stub provider via TestClient, proving the
save -> list/search -> get surface, the `from-prompt` insert (a saved prompt
running as a chat turn, streamed as SSE), and the RBAC boundary around it all.
"""
import json

from starlette.testclient import TestClient

from api.main import app


def _create_conv(client, headers, workspace_id, title="t"):
    resp = client.post(
        "/conversations",
        json={"workspace_id": workspace_id, "title": title},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_prompt_crud_and_search(make_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        created = client.post(
            f"/workspaces/{wid}/prompts",
            json={"title": "Triage", "body": "find root cause", "tags": ["Debug"]},
            headers=headers,
        ).json()
        assert created["tags"] == ["debug"]
        assert created["author_id"] == uid  # identity is server-derived
        pid = created["id"]

        got = client.get(f"/prompts/{pid}", headers=headers).json()
        assert got["body"] == "find root cause"

        listed = client.get(
            f"/workspaces/{wid}/prompts", params={"tag": "debug"}, headers=headers
        ).json()
        assert any(p["id"] == pid for p in listed["prompts"])

        searched = client.get(
            f"/workspaces/{wid}/prompts", params={"q": "root cause"}, headers=headers
        ).json()
        assert any(p["id"] == pid for p in searched["prompts"])

        assert client.get("/prompts/missing", headers=headers).status_code == 404


def test_prompt_routes_require_auth_and_membership(make_workspace, make_user):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        pid = client.post(
            f"/workspaces/{wid}/prompts",
            json={"title": "Q", "body": "b"},
            headers=headers,
        ).json()["id"]

        # No token -> 401.
        assert client.get(f"/workspaces/{wid}/prompts").status_code == 401
        assert client.post(
            f"/workspaces/{wid}/prompts", json={"title": "x", "body": "y"}
        ).status_code == 401

        # A member of a *different* workspace can't list, save into, or even
        # fetch this workspace's prompts by id (404, no probing).
        outsider, _ = make_user(client)
        assert client.get(f"/workspaces/{wid}/prompts", headers=outsider).status_code == 404
        assert client.post(
            f"/workspaces/{wid}/prompts", json={"title": "x", "body": "y"}, headers=outsider
        ).status_code == 404
        assert client.get(f"/prompts/{pid}", headers=outsider).status_code == 404


def test_observer_can_browse_but_not_save(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        obs_headers, _ = join_workspace(client, owner_headers, wid, role="observer")

        assert client.get(f"/workspaces/{wid}/prompts", headers=obs_headers).status_code == 200
        assert client.post(
            f"/workspaces/{wid}/prompts",
            json={"title": "nope", "body": "nope"},
            headers=obs_headers,
        ).status_code == 403


def test_insert_prompt_runs_as_conversation_turn(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        pid = client.post(
            f"/workspaces/{wid}/prompts",
            json={"title": "Q", "body": "What are the tradeoffs?"},
            headers=headers,
        ).json()["id"]
        branch_id = _create_conv(client, headers, wid)["branch_id"]

        resp = client.post(
            f"/conversations/{branch_id}/messages/from-prompt",
            json={"prompt_id": pid},
            headers=headers,
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


def test_insert_missing_prompt_is_404(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        branch_id = _create_conv(client, headers, wid)["branch_id"]
        resp = client.post(
            f"/conversations/{branch_id}/messages/from-prompt",
            json={"prompt_id": "nope"},
            headers=headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


def test_insert_prompt_from_other_workspace_is_404(make_workspace):
    """A prompt id from another tenant can't be run in this workspace's thread."""
    with TestClient(app) as client:
        headers_a, _, wid_a = make_workspace(client)
        headers_b, _, wid_b = make_workspace(client)
        foreign_pid = client.post(
            f"/workspaces/{wid_b}/prompts",
            json={"title": "theirs", "body": "secret sauce"},
            headers=headers_b,
        ).json()["id"]
        branch_id = _create_conv(client, headers_a, wid_a)["branch_id"]

        resp = client.post(
            f"/conversations/{branch_id}/messages/from-prompt",
            json={"prompt_id": foreign_pid},
            headers=headers_a,
        )
        assert resp.status_code == 404


def test_prompt_edit_and_delete_author_or_owner_only(make_workspace, join_workspace):
    with TestClient(app) as client:
        owner_headers, _oid, wid = make_workspace(client)
        author_headers, _aid = join_workspace(client, owner_headers, wid)
        other_headers, _xid = join_workspace(client, owner_headers, wid)

        pid = client.post(
            f"/workspaces/{wid}/prompts",
            json={"title": "typo'd titel", "body": "draft", "tags": ["review"]},
            headers=author_headers,
        ).json()["id"]

        # A non-author collaborator can neither edit nor delete.
        denied = client.patch(
            f"/prompts/{pid}",
            json={"title": "hijack", "body": "x"},
            headers=other_headers,
        )
        assert denied.status_code == 403
        assert client.delete(f"/prompts/{pid}", headers=other_headers).status_code == 403

        # The author fixes the typo.
        fixed = client.patch(
            f"/prompts/{pid}",
            json={"title": "fixed title", "body": "final", "tags": ["review", "Final"]},
            headers=author_headers,
        )
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["title"] == "fixed title"
        assert fixed.json()["tags"] == ["review", "final"]  # tags stay normalised

        # The workspace owner can delete anyone's prompt.
        deleted = client.delete(f"/prompts/{pid}", headers=owner_headers)
        assert deleted.status_code == 200, deleted.text
        assert client.get(f"/prompts/{pid}", headers=owner_headers).status_code == 404


def test_demotion_to_observer_revokes_write_over_your_own_prompts(
    make_workspace, join_workspace
):
    """Authorship is not a standing grant.

    Creating a prompt needs Collaborator, so an Observer can never author one —
    but a Collaborator who wrote prompts and was then demoted kept edit and
    delete rights over them, which contradicts both the role model and the
    permission matrix the app displays.
    """
    with TestClient(app) as client:
        owner_headers, owner_id, wid = make_workspace(client)
        mate_headers, mate_id = join_workspace(client, owner_headers, wid)

        created = client.post(
            f"/workspaces/{wid}/prompts",
            json={"title": "Chunking", "body": "chunk at 500", "tags": []},
            headers=mate_headers,
        )
        assert created.status_code == 200, created.text
        pid = created.json()["id"]

        # As a Collaborator, their own prompt is theirs to change.
        assert client.patch(
            f"/prompts/{pid}",
            json={"title": "Chunking v2", "body": "chunk at 600", "tags": []},
            headers=mate_headers,
        ).status_code == 200

        # Demote them.
        assert client.patch(
            f"/api/workspaces/{wid}/members/{mate_id}",
            json={"role": "observer"},
            headers=owner_headers,
        ).status_code == 200

        # Reading stays open; writing does not — not even over their own work.
        assert client.get(f"/prompts/{pid}", headers=mate_headers).status_code == 200
        assert client.patch(
            f"/prompts/{pid}",
            json={"title": "sneak", "body": "x", "tags": []},
            headers=mate_headers,
        ).status_code == 403
        assert client.delete(f"/prompts/{pid}", headers=mate_headers).status_code == 403

        # The owner can still clean it up.
        assert client.delete(f"/prompts/{pid}", headers=owner_headers).status_code == 200


def test_an_outsider_still_cannot_probe_prompt_ids(make_workspace, make_user):
    """The role floor must not turn a tenancy 404 into an informative 403."""
    with TestClient(app) as client:
        owner_headers, _, wid = make_workspace(client)
        pid = client.post(
            f"/workspaces/{wid}/prompts",
            json={"title": "T", "body": "B", "tags": []},
            headers=owner_headers,
        ).json()["id"]

        outsider, _ = make_user(client)
        assert client.patch(
            f"/prompts/{pid}", json={"title": "x", "body": "y", "tags": []}, headers=outsider
        ).status_code == 404
        assert client.delete(f"/prompts/{pid}", headers=outsider).status_code == 404
