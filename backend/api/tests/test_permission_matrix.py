"""The permission matrix the app renders must be true.

`MembersView` draws a table of who may do what, straight from the client's
`MATRIX` in `frontend/app/src/lib/rbac.ts`. That table is the product's public
statement of its own policy — but it is rendered from *client* data, so if the
server's enforcement ever drifts from it, the app displays a confident lie to
the very people relying on it.

This exercises the real endpoints as a real Observer and a real Collaborator
and asserts each cell. The expected table below is a transcription of
`MATRIX`; if you change one, this fails until you change the other.

`run.control` is not covered: steering or killing takes a run id, and the
handler looks the run up before it checks the role, so a non-existent run is a
404 for everyone and the role gate cannot be observed without a live run. Its
gating is asserted directly in the conversation router tests instead.
"""
import pytest
from starlette.testclient import TestClient

from api.main import app

# Transcribed from frontend/app/src/lib/rbac.ts — keep the two in step.
OBSERVER_MAY = {
    "conversation.read": True,
    "message.send": False,
    "branch.fork": False,
    "prompt.write": False,
    "document.write": False,
    "run.escalate": False,
    "member.manage": False,
    "workspace.manage": False,
    "permission.edit": False,
}
COLLABORATOR_MAY = {
    "conversation.read": True,
    "message.send": True,
    "branch.fork": True,
    "prompt.write": True,
    "document.write": True,
    "run.escalate": True,
    "member.manage": False,
    "workspace.manage": False,
    "permission.edit": False,
}


def _attempt(client, action, headers, *, wid, cid, branch_id, node_id, victim_id):
    """Perform `action` and return whether the server allowed it."""
    if action == "conversation.read":
        r = client.get(f"/conversations/branches/{branch_id}/history", headers=headers)
    elif action == "message.send":
        r = client.post(f"/conversations/{branch_id}/messages", json={"prompt": "hi"}, headers=headers)
    elif action == "branch.fork":
        r = client.post(f"/conversations/{cid}/fork",
                        json={"from_node_id": node_id, "name": "alt"}, headers=headers)
    elif action == "prompt.write":
        r = client.post(f"/workspaces/{wid}/prompts",
                        json={"title": "T", "body": "B", "tags": []}, headers=headers)
    elif action == "document.write":
        r = client.post(f"/api/workspaces/{wid}/documents",
                        files={"file": ("n.md", b"# hi", "text/markdown")}, headers=headers)
    elif action == "run.escalate":
        r = client.post(f"/conversations/{branch_id}/deep", json={"prompt": "hard"}, headers=headers)
    elif action == "member.manage":
        r = client.post(f"/api/workspaces/{wid}/invites", json={"role": "collaborator"}, headers=headers)
    elif action == "workspace.manage":
        r = client.patch(f"/api/workspaces/{wid}", json={"name": "renamed"}, headers=headers)
    elif action == "permission.edit":
        r = client.patch(f"/api/workspaces/{wid}/members/{victim_id}",
                         json={"role": "observer"}, headers=headers)
    else:  # pragma: no cover - the table and this function are edited together
        raise AssertionError(f"no attempt defined for {action}")
    assert r.status_code != 404, f"{action}: 404 means the fixture is wrong, not the policy"
    return r.status_code not in (401, 403)


@pytest.mark.parametrize(
    "role,expected",
    [("observer", OBSERVER_MAY), ("collaborator", COLLABORATOR_MAY)],
    ids=["observer", "collaborator"],
)
def test_the_displayed_matrix_matches_what_the_server_enforces(
    make_workspace, join_workspace, role, expected
):
    with TestClient(app) as client:
        owner_headers, _oid, wid = make_workspace(client)
        created = client.post(
            "/conversations", json={"workspace_id": wid, "title": "demo"}, headers=owner_headers
        ).json()
        cid, branch_id = created["conversation_id"], created["branch_id"]
        client.post(f"/conversations/{branch_id}/messages",
                    json={"prompt": "seed"}, headers=owner_headers)
        node_id = client.get(
            f"/conversations/branches/{branch_id}/history", headers=owner_headers
        ).json()["nodes"][0]["id"]

        headers, uid = join_workspace(client, owner_headers, wid, role=role)
        # permission.edit targets someone else, so the owner-protection rule
        # cannot be mistaken for the role gate.
        victim_headers, victim_id = join_workspace(client, owner_headers, wid, role="observer")

        wrong = []
        for action, may in expected.items():
            allowed = _attempt(
                client, action, headers,
                wid=wid, cid=cid, branch_id=branch_id, node_id=node_id, victim_id=victim_id,
            )
            if allowed != may:
                wrong.append(
                    f"{action}: the app tells users a {role} "
                    f"{'may' if may else 'may not'}, the server "
                    f"{'allowed' if allowed else 'refused'} it"
                )
        assert not wrong, "The permission matrix is lying:\n  " + "\n  ".join(wrong)
