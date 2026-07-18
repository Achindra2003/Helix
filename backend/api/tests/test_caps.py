"""Abuse caps (P2): workspaces per user, members per workspace, invite
redemptions, and request body size.

These are ceilings, not business rules — every one sits far above honest use.
The tests lower them so the boundary is reachable, and check the *boundary*
(allowed right up to the limit, refused past it) rather than just the refusal,
since an off-by-one here silently costs a user their last allowed workspace.
"""
import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app
from api.models import Invite


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cap(monkeypatch):
    """Temporarily lower a cap; restored automatically after the test."""

    def _set(name: str, value: int):
        monkeypatch.setattr(settings, name, value)

    return _set


# --- workspaces per user ------------------------------------------------------


def test_workspace_cap_allows_up_to_the_limit_then_refuses(client, make_user, cap):
    cap("max_workspaces_per_user", 2)
    headers, _ = make_user(client)

    for i in range(2):
        ok = client.post("/api/workspaces", json={"name": f"WS {i}"}, headers=headers)
        assert ok.status_code == 201, ok.text

    refused = client.post("/api/workspaces", json={"name": "one too many"}, headers=headers)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "limit_reached"


def test_workspace_cap_counts_only_workspaces_you_own(client, make_user, cap):
    """Being invited into many workspaces is normal and must stay unbounded."""
    cap("max_workspaces_per_user", 1)
    owner_headers, _ = make_user(client)
    joiner_headers, _ = make_user(client)

    ws = client.post("/api/workspaces", json={"name": "Owned"}, headers=owner_headers)
    assert ws.status_code == 201
    ws_id = ws.json()["id"]

    # The joiner owns one workspace of their own...
    own = client.post("/api/workspaces", json={"name": "Theirs"}, headers=joiner_headers)
    assert own.status_code == 201

    # ...and can still be invited into someone else's, despite being at the cap.
    invite = client.post(f"/api/workspaces/{ws_id}/invites", headers=owner_headers)
    token = invite.json()["token"]
    joined = client.post(f"/api/invites/{token}/accept", headers=joiner_headers)
    assert joined.status_code == 200, joined.text


def test_cap_of_zero_disables_the_limit(client, make_user, cap):
    cap("max_workspaces_per_user", 0)
    headers, _ = make_user(client)
    for i in range(4):
        assert (
            client.post("/api/workspaces", json={"name": f"W{i}"}, headers=headers).status_code
            == 201
        )


# --- members per workspace ----------------------------------------------------


def test_member_cap_refuses_the_join_past_the_limit(client, make_workspace, make_user, cap):
    owner_headers, _, ws_id = make_workspace(client)
    invite = client.post(f"/api/workspaces/{ws_id}/invites", headers=owner_headers)
    token = invite.json()["token"]

    # The owner already occupies the single available seat.
    cap("max_members_per_workspace", 1)
    joiner_headers, _ = make_user(client)
    refused = client.post(f"/api/invites/{token}/accept", headers=joiner_headers)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "limit_reached"


def test_existing_member_reopening_a_link_is_never_turned_away(
    client, make_workspace, cap
):
    """A full workspace must not lock out the people already in it."""
    owner_headers, _, ws_id = make_workspace(client)
    invite = client.post(f"/api/workspaces/{ws_id}/invites", headers=owner_headers)
    token = invite.json()["token"]

    cap("max_members_per_workspace", 1)
    again = client.post(f"/api/invites/{token}/accept", headers=owner_headers)
    assert again.status_code == 200, again.text


# --- invite redemptions -------------------------------------------------------


def test_invite_is_dead_once_its_uses_are_spent(client, make_workspace, make_user, cap):
    cap("invite_max_uses", 1)
    owner_headers, _, ws_id = make_workspace(client)
    invite = client.post(f"/api/workspaces/{ws_id}/invites", headers=owner_headers)
    token = invite.json()["token"]

    first_headers, _ = make_user(client)
    assert client.post(f"/api/invites/{token}/accept", headers=first_headers).status_code == 200

    second_headers, _ = make_user(client)
    spent = client.post(f"/api/invites/{token}/accept", headers=second_headers)
    assert spent.status_code == 404

    # And it is gone from the preview surface too, not merely from accept.
    assert client.get(f"/api/invites/{token}").status_code == 404


def test_rejoining_does_not_consume_a_use(client, make_workspace, make_user, cap):
    """Otherwise one indecisive member could burn a whole invite's budget."""
    cap("invite_max_uses", 2)
    owner_headers, _, ws_id = make_workspace(client)
    invite = client.post(f"/api/workspaces/{ws_id}/invites", headers=owner_headers)
    token = invite.json()["token"]

    joiner_headers, _ = make_user(client)
    for _ in range(3):
        assert (
            client.post(f"/api/invites/{token}/accept", headers=joiner_headers).status_code
            == 200
        )

    # One seat consumed, one still available for someone new.
    newcomer_headers, _ = make_user(client)
    assert (
        client.post(f"/api/invites/{token}/accept", headers=newcomer_headers).status_code == 200
    )


def test_legacy_invites_with_no_budget_stay_unlimited():
    """Rows predating this column get max_uses = 0 from the DB shim. Adding the
    cap must not retroactively kill invite links that are already circulating."""
    legacy = Invite(token="t", workspace_id="w", created_by="u", max_uses=0, uses=999)
    assert not legacy.is_exhausted


# --- request body size --------------------------------------------------------


def test_oversized_prompt_is_refused_before_the_handler(client, make_workspace, cap):
    cap("max_message_bytes", 1_000)
    owner_headers, _, _ = make_workspace(client)

    huge = client.post(
        "/conversations/some-branch-id/messages",
        json={"prompt": "x" * 5_000},
        headers=owner_headers,
    )
    assert huge.status_code == 413
    assert huge.json()["error"]["code"] == "payload_too_large"


def test_normal_sized_prompt_is_not_affected(client, make_workspace):
    """The cap must be invisible in ordinary use — a 413 here would mean the
    limit is set absurdly low."""
    owner_headers, _, _ = make_workspace(client)
    resp = client.post(
        "/conversations/does-not-exist/messages",
        json={"prompt": "a normal question"},
        headers=owner_headers,
    )
    assert resp.status_code != 413


def test_uploads_keep_their_larger_ceiling():
    """Document routes must not inherit the tight prompt cap, or file grounding
    breaks. Checked at the resolver so no 8 MB body is actually sent."""
    from api.main import _body_limit_for

    assert _body_limit_for("/api/workspaces/w1/documents") == settings.max_request_bytes
    assert _body_limit_for("/conversations/b1/messages") == settings.max_message_bytes
    assert _body_limit_for("/conversations/b1/deep") == settings.max_message_bytes
    assert _body_limit_for("/conversations/b1/agent") == settings.max_message_bytes
