"""Password reset (P4).

The properties worth testing here are the security ones, not the happy path:
the endpoint must not reveal who has an account, and a link must not work
twice. Both are easy to write correctly and easy to regress silently.

Email is never configured in tests, so `api.email.send` no-ops and returns
False. The token is read from the call it *would* have made.
"""
import pytest
from fastapi.testclient import TestClient

from api import email as email_module
from api.config import settings
from api.main import app
from api.security import make_reset_token


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing email instead of sending it."""
    outbox = []

    async def fake_send(*, to, subject, text):
        outbox.append({"to": to, "subject": subject, "text": text})
        return True

    monkeypatch.setattr(email_module, "send", fake_send)
    # The router imported the symbol directly, so patch it there too.
    from api.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "send_email", fake_send)
    return outbox


def _register(client, email="reset@test.dev", password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def _token_from(outbox):
    assert outbox, "no email was sent"
    body = outbox[-1]["text"]
    marker = "token="
    start = body.index(marker) + len(marker)
    return body[start:].split()[0]


def test_reset_flow_end_to_end(client, sent):
    _register(client, "flow@test.dev", "original-pw")

    r = client.post("/api/auth/forgot-password", json={"email": "flow@test.dev"})
    assert r.status_code == 202

    token = _token_from(sent)
    r = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pw"}
    )
    assert r.status_code == 204

    # The new password works and the old one does not.
    assert (
        client.post(
            "/api/auth/login", json={"email": "flow@test.dev", "password": "brand-new-pw"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "flow@test.dev", "password": "original-pw"}
        ).status_code
        == 401
    )


def test_unknown_address_is_indistinguishable_from_a_known_one(client, sent):
    """Otherwise this endpoint is an account enumerator: submit a list of
    addresses, learn which are registered. The status and body must match."""
    _register(client, "known@test.dev")

    known = client.post("/api/auth/forgot-password", json={"email": "known@test.dev"})
    unknown = client.post(
        "/api/auth/forgot-password", json={"email": "nobody@test.dev"}
    )

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    # ...and only the real account actually got mail.
    assert [m["to"] for m in sent] == ["known@test.dev"]


def test_a_reset_link_works_only_once(client, sent):
    """The link lives in an inbox, which is not a secure place. Using it must
    burn it — here, because the signing key includes the password hash it
    replaced."""
    _register(client, "once@test.dev", "original-pw")
    client.post("/api/auth/forgot-password", json={"email": "once@test.dev"})
    token = _token_from(sent)

    first = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "first-reset"}
    )
    assert first.status_code == 204

    second = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "second-reset"}
    )
    assert second.status_code == 400
    # The first reset still stands.
    assert (
        client.post(
            "/api/auth/login", json={"email": "once@test.dev", "password": "first-reset"}
        ).status_code
        == 200
    )


def test_outstanding_links_die_when_one_is_used(client, sent):
    """Two requests, then a reset with the newer link: the older must be dead
    too, or a stale email stays a live credential."""
    _register(client, "two@test.dev", "original-pw")
    client.post("/api/auth/forgot-password", json={"email": "two@test.dev"})
    older = _token_from(sent)
    client.post("/api/auth/forgot-password", json={"email": "two@test.dev"})
    newer = _token_from(sent)

    assert (
        client.post(
            "/api/auth/reset-password",
            json={"token": newer, "new_password": "newer-wins"},
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/auth/reset-password",
            json={"token": older, "new_password": "older-should-fail"},
        ).status_code
        == 400
    )


def test_a_session_token_is_not_a_reset_token(client, sent):
    """They are both JWTs signed by this server. Without a type check, a stolen
    session token would silently double as a password-change credential."""
    auth = _register(client, "typed@test.dev")
    session_token = auth["token"]

    r = client.post(
        "/api/auth/reset-password",
        json={"token": session_token, "new_password": "should-not-work"},
    )
    assert r.status_code == 400


def test_a_reset_token_is_not_a_session_token(client, sent):
    """The other direction: the emailed link must not authenticate API calls."""
    auth = _register(client, "notasession@test.dev")
    reset = make_reset_token(auth["user"]["id"], "irrelevant-hash")
    r = client.get("/api/me", headers={"Authorization": f"Bearer {reset}"})
    assert r.status_code == 401


def test_expired_link_is_refused(client, sent, monkeypatch):
    monkeypatch.setattr(settings, "password_reset_ttl_minutes", -1)
    _register(client, "expired@test.dev")
    client.post("/api/auth/forgot-password", json={"email": "expired@test.dev"})
    token = _token_from(sent)

    r = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "too-late"}
    )
    assert r.status_code == 400


def test_garbage_token_is_refused(client):
    r = client.post(
        "/api/auth/reset-password",
        json={"token": "not-a-jwt", "new_password": "whatever123"},
    )
    assert r.status_code == 400
