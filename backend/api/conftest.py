"""Hermetic test environment.

Set BEFORE any `api` import (pytest loads this conftest before collecting the
test modules under it, and environment variables outrank `.env` values in
pydantic-settings). Without this, a developer's `.env` leaks into the suite —
`LLM_PROVIDER=groq` made the streaming tests silently hit the live Groq API,
and the dev `helix.db` accumulated test rows.
"""
import os
from pathlib import Path

os.environ["LLM_PROVIDER"] = "stub"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_helix.db"
os.environ["GROQ_API_KEY"] = ""
os.environ["JWT_SECRET"] = "test-secret"
# Rate limiting off by default: the suite registers hundreds of users from one
# client, which is indistinguishable from the abuse the limiter exists to stop.
# The limiter's own tests switch it back on explicitly (api/tests/
# test_rate_limit.py), so the behaviour is still covered — just not imposed on
# every other test.
os.environ["RATE_LIMIT_ENABLED"] = "0"
# Example-workspace seeding off by default too: the suite registers hundreds of
# users, most of them to test something unrelated, and a seeded workspace would
# add embedding work to each one and change what "a new user's workspaces"
# means for every test that counts them. api/tests/test_onboarding.py turns it
# back on explicitly.
os.environ["SEED_EXAMPLE_WORKSPACE"] = "0"

# Fresh DB per test session (delete up front; leave the file behind afterwards
# for post-mortem inspection).
_test_db = Path(__file__).resolve().parent.parent / "test_helix.db"
if _test_db.exists():
    _test_db.unlink()


import uuid

import pytest


@pytest.fixture
def make_user():
    """Factory: register a fresh user through the real API.

    Returns ``(headers, user_id)`` where headers carry the Bearer token — the
    identity every gated route now derives server-side.
    """

    def _make(client, email: str | None = None):
        email = email or f"u-{uuid.uuid4().hex[:10]}@test.dev"
        resp = client.post(
            "/api/auth/register", json={"email": email, "password": "pw123456"}
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]

    return _make


@pytest.fixture
def make_workspace(make_user):
    """Factory: a fresh owner + workspace. Returns ``(headers, user_id, workspace_id)``."""

    def _make(client):
        headers, uid = make_user(client)
        ws = client.post(
            "/api/workspaces", json={"name": "Test WS"}, headers=headers
        )
        assert ws.status_code == 201, ws.text
        return headers, uid, ws.json()["id"]

    return _make


@pytest.fixture
def join_workspace(make_user):
    """Factory: add a fresh user to a workspace via a real invite.

    ``role`` may be collaborator (default) or observer — exercising the
    invite-role path. Returns ``(headers, user_id)`` for the joiner.
    """

    def _join(client, owner_headers, workspace_id, role="collaborator"):
        inv = client.post(
            f"/api/workspaces/{workspace_id}/invites",
            json={"role": role},
            headers=owner_headers,
        )
        assert inv.status_code == 201, inv.text
        token = inv.json()["token"]
        headers, uid = make_user_inner(client)
        acc = client.post(f"/api/invites/{token}/accept", headers=headers)
        assert acc.status_code == 200, acc.text
        return headers, uid

    make_user_inner = make_user
    return _join
