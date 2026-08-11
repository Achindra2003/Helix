"""Invite-only mode: the setting that makes a private install possible.

Until now `/auth/register` was unconditional, so a team putting Helix on their
LAN had open signup and nothing to turn it off with. `ALLOW_REGISTRATION=0`
closes it — but not by refusing everyone, because the product already hands out
`/invite/{token}` links and a person following one has no account yet. So a
usable invite is what admits you, and the invite machinery that already exists
(role, expiry, use budget, revocation) becomes the admission control.

The two properties worth pinning down are therefore: a stranger cannot get in,
and an invited teammate still can.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def closed(monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)


@pytest.fixture
def close_later(monkeypatch):
    """Close registration part-way through a test.

    The tests that need an invite need an owner to issue it, and an owner is
    made by registering — so those cannot start from a closed instance. This is
    also the real sequence an operator follows: stand the instance up, make the
    accounts that belong there, then shut the door.
    """
    return lambda: monkeypatch.setattr(settings, "allow_registration", False)


def _email() -> str:
    return f"u-{uuid.uuid4().hex[:10]}@test.dev"


def _register(client, invite: str | None = None):
    body = {"email": _email(), "password": "pw123456"}
    if invite is not None:
        body["invite"] = invite
    return client.post("/api/auth/register", json=body)


def _invite(client, owner_headers, workspace_id, role="collaborator"):
    r = client.post(
        f"/api/workspaces/{workspace_id}/invites",
        json={"role": role},
        headers=owner_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


# --- open (the default) -------------------------------------------------------

def test_registration_is_open_by_default(client):
    """Someone has to be able to get into a fresh instance."""
    assert _register(client).status_code == 201


# --- closed -------------------------------------------------------------------

def test_closed_instance_refuses_a_stranger(client, closed):
    r = _register(client)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "registration_closed"


def test_closed_instance_refuses_a_made_up_invite(client, closed):
    assert _register(client, invite="not-a-real-token").status_code == 403


def test_closed_instance_refuses_an_empty_invite(client, closed):
    """`""` is falsy — the guard must not read that as "no check needed"."""
    assert _register(client, invite="").status_code == 403


def test_an_invited_teammate_can_still_register(client, close_later, make_workspace):
    """The whole point: closing signup must not break the invite links the
    product issues, or invite-only would mean nobody can ever join."""
    owner_headers, _uid, ws_id = make_workspace(client)
    token = _invite(client, owner_headers, ws_id)
    close_later()

    r = _register(client, invite=token)
    assert r.status_code == 201, r.text

    # …and the invite still works afterwards, because registering does not
    # redeem it.
    joiner = {"Authorization": f"Bearer {r.json()['token']}"}
    acc = client.post(f"/api/invites/{token}/accept", headers=joiner)
    assert acc.status_code == 200, acc.text
    assert acc.json()["id"] == ws_id


def test_registering_does_not_spend_a_use(client, close_later, make_workspace):
    """A failed or abandoned sign-up must not burn the link. Registration
    checks the invite; only /accept spends it."""
    owner_headers, _uid, ws_id = make_workspace(client)
    token = _invite(client, owner_headers, ws_id)
    close_later()

    first = _register(client, invite=token)
    assert first.status_code == 201
    # Same link, a second person, before either has accepted.
    assert _register(client, invite=token).status_code == 201


def test_a_revoked_invite_stops_admitting(client, close_later, make_workspace):
    owner_headers, _uid, ws_id = make_workspace(client)
    token = _invite(client, owner_headers, ws_id)
    close_later()
    assert (
        client.delete(
            f"/api/workspaces/{ws_id}/invites/{token}", headers=owner_headers
        ).status_code
        == 204
    )
    assert _register(client, invite=token).status_code == 403


def test_login_is_unaffected(client, make_workspace, monkeypatch):
    """Closing signup must not lock out the accounts that already exist."""
    email, password = _email(), "pw123456"
    assert (
        client.post(
            "/api/auth/register", json={"email": email, "password": password}
        ).status_code
        == 201
    )
    monkeypatch.setattr(settings, "allow_registration", False)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200


# --- what the login screen reads ---------------------------------------------

def test_public_config_reports_the_posture(client, closed):
    assert client.get("/api/public-config").json()["registration_open"] is False


def test_public_config_reports_open_by_default(client):
    assert client.get("/api/public-config").json()["registration_open"] is True
