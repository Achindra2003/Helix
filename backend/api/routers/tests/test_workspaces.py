"""Workspace lifecycle: rename, cascading delete, and leave.

No DB-level FK cascades exist in this schema (see api/models.py's docstring),
so delete_workspace's manual cascade is the thing actually worth proving —
not just that the workspace row disappears, but that it doesn't error out
with real conversations/nodes/documents hanging off it.
"""
from starlette.testclient import TestClient

import api.routers.workspaces as workspaces_mod
from api.conversation.embeddings import EmbeddingIndex
from api.db import SessionLocal
from api.main import app


class _ForceMatchMemory:
    """Everything matches everything — deterministic retrieval, no real
    embedder/network dependency (same pattern as the injection-regression
    suite's fake `Mem`)."""

    class _E:
        name = "test"

        def embed(self, texts):
            return [[1.0] for _ in texts]

    def get_embedder(self):
        return self._E()

    @staticmethod
    def cosine_similarity(a, b):
        return 1.0


def test_owner_can_rename_workspace_member_cannot(make_workspace, join_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, headers, wid)

        renamed = client.patch(
            f"/api/workspaces/{wid}", json={"name": "New Name"}, headers=headers
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "New Name"

        denied = client.patch(
            f"/api/workspaces/{wid}", json={"name": "Nope"}, headers=member_headers
        )
        assert denied.status_code == 403


def test_delete_workspace_cascades_conversations_and_is_owner_only(
    make_workspace, join_workspace
):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, headers, wid)

        # Real data hanging off the workspace: a conversation with a sent turn.
        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t", "visibility": "shared"},
            headers=headers,
        )
        assert conv.status_code == 200, conv.text
        branch_id = conv.json()["branch_id"]
        sent = client.post(
            f"/conversations/{branch_id}/messages",
            json={"prompt": "hello"},
            headers=headers,
        )
        assert sent.status_code == 200, sent.text

        # A non-owner cannot delete.
        denied = client.delete(f"/api/workspaces/{wid}", headers=member_headers)
        assert denied.status_code == 403

        # The owner can, even with live data in the tree.
        deleted = client.delete(f"/api/workspaces/{wid}", headers=headers)
        assert deleted.status_code == 204, deleted.text

        gone = client.get(f"/api/workspaces/{wid}", headers=headers)
        assert gone.status_code == 404


def test_search_finds_relevant_messages_and_respects_private_visibility(
    make_workspace, join_workspace, monkeypatch
):
    monkeypatch.setattr(
        workspaces_mod, "_search_index",
        EmbeddingIndex(SessionLocal, memory=_ForceMatchMemory()),
    )
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, headers, wid)

        shared = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "shared", "visibility": "shared"},
            headers=headers,
        ).json()
        client.post(
            f"/conversations/{shared['branch_id']}/messages",
            json={"prompt": "migrate the database to postgres"},
            headers=headers,
        )

        private = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "secret", "visibility": "private"},
            headers=headers,
        ).json()
        client.post(
            f"/conversations/{private['branch_id']}/messages",
            json={"prompt": "confidential budget notes"},
            headers=headers,
        )

        # The author sees both their shared and their own private thread.
        as_owner = client.post(
            f"/api/workspaces/{wid}/search", json={"query": "anything"}, headers=headers
        )
        assert as_owner.status_code == 200, as_owner.text
        owner_conv_ids = {i["conversation_id"] for i in as_owner.json()["items"]}
        assert shared["conversation_id"] in owner_conv_ids
        assert private["conversation_id"] in owner_conv_ids

        # A teammate sees the shared thread, never the private one.
        as_member = client.post(
            f"/api/workspaces/{wid}/search", json={"query": "anything"}, headers=member_headers
        )
        member_conv_ids = {i["conversation_id"] for i in as_member.json()["items"]}
        assert shared["conversation_id"] in member_conv_ids
        assert private["conversation_id"] not in member_conv_ids


def test_usage_reports_chat_tokens_from_sent_messages(make_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)

        zero = client.get(f"/api/workspaces/{wid}/usage", headers=headers)
        assert zero.status_code == 200, zero.text
        body = zero.json()
        assert body["chat_tokens_approx"] == 0
        assert body["deep_run_tokens"] == 0
        assert body["calls"] == [] and body["estimated_cost_usd"] is None

        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t", "visibility": "shared"},
            headers=headers,
        ).json()
        client.post(
            f"/conversations/{conv['branch_id']}/messages",
            json={"prompt": "hello"},
            headers=headers,
        )

        after = client.get(f"/api/workspaces/{wid}/usage", headers=headers).json()
        assert after["chat_tokens_approx"] > 0
        assert after["deep_run_tokens"] == 0  # no deep run in this test


def test_owner_can_remove_a_member_but_not_themselves(make_workspace, join_workspace):
    with TestClient(app) as client:
        headers, uid, wid = make_workspace(client)
        member_headers, mid = join_workspace(client, headers, wid)

        # A collaborator can't kick anyone.
        denied = client.delete(f"/api/workspaces/{wid}/members/{uid}", headers=member_headers)
        assert denied.status_code == 403

        # The owner can't be removed (even by themselves — that's delete-workspace).
        blocked = client.delete(f"/api/workspaces/{wid}/members/{uid}", headers=headers)
        assert blocked.status_code == 409

        # The owner removes the member; the workspace 404s for them afterwards.
        kicked = client.delete(f"/api/workspaces/{wid}/members/{mid}", headers=headers)
        assert kicked.status_code == 204, kicked.text
        assert client.get(f"/api/workspaces/{wid}", headers=member_headers).status_code == 404


def test_invites_can_be_listed_and_revoked(make_workspace, make_user):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        token = client.post(
            f"/api/workspaces/{wid}/invites", json={"role": "collaborator"}, headers=headers
        ).json()["token"]

        listed = client.get(f"/api/workspaces/{wid}/invites", headers=headers)
        assert listed.status_code == 200, listed.text
        assert [i["token"] for i in listed.json()["items"]] == [token]

        revoked = client.delete(f"/api/workspaces/{wid}/invites/{token}", headers=headers)
        assert revoked.status_code == 204
        assert client.get(f"/api/workspaces/{wid}/invites", headers=headers).json()["items"] == []

        # A revoked token no longer admits anyone.
        joiner_headers, _jid = make_user(client)
        assert client.post(f"/api/invites/{token}/accept", headers=joiner_headers).status_code == 404


def test_leave_workspace_member_can_owner_cannot(make_workspace, join_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, headers, wid)

        left = client.post(f"/api/workspaces/{wid}/leave", headers=member_headers)
        assert left.status_code == 204, left.text
        # No longer a member: the workspace 404s for them now.
        after = client.get(f"/api/workspaces/{wid}", headers=member_headers)
        assert after.status_code == 404

        blocked = client.post(f"/api/workspaces/{wid}/leave", headers=headers)
        assert blocked.status_code == 409
