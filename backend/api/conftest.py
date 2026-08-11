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
# SQLite unless the caller names a database. This one line is why the Postgres
# breakage survived: the URL used to be set unconditionally, so all 356 tests
# ran against SQLite and *could not* be pointed anywhere else. SQLite accepts a
# tz-aware datetime into a naive column; Postgres rejects it, which meant the
# suite was green against a schema the production database refuses.
#
# `TEST_DATABASE_URL` is the seam. CI sets it to a throwaway Postgres (see
# .github/workflows/ci.yml, job `backend-postgres`) and runs the identical
# suite, so a dialect-specific defect fails a build instead of a deploy.
#
# The process id is in the filename because this file *deletes* the database it
# is about to use, and two pytest processes sharing one path means the second
# one deletes the first one's database mid-run. Most tests survive that — every
# TestClient's lifespan calls create_all, so the next one rebuilds the tables —
# which is what made it so confusing: the failure only lands when the deletion
# falls inside a test that already wrote a row, and it surfaces as
# `no such table: users` in whichever test happened to be running. It reads as
# a product bug in an innocent test, and it moves every time.
#
# That is not a hypothetical: running one focused test while a full suite is in
# flight does it, and so does any CI job that runs two pytest invocations over
# one checkout at the same time.
_TEST_DB_NAME = f"test_helix-{os.getpid()}.db"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite+aiosqlite:///./{_TEST_DB_NAME}"
)
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

if os.environ["DATABASE_URL"].startswith("sqlite"):
    # Fresh DB per test session (delete up front; leave the file behind
    # afterwards for post-mortem inspection — see pytest_sessionfinish, which
    # keeps it only when there is something to inspect).
    #
    # Resolved against the working directory, because that is what the relative
    # URL above resolves against. It used to be resolved against this file's
    # parent, so running pytest from anywhere but `backend/` deleted one
    # database and then used a different, stale one.
    _test_db = Path.cwd() / _TEST_DB_NAME
    if _test_db.exists():
        _test_db.unlink()
else:
    # Every `TestClient` runs the app in its own event loop, and an asyncpg
    # connection is bound to the loop that opened it. One module-level engine
    # pooling across all of them fails the moment the second client starts.
    os.environ["DB_NO_POOL"] = "1"

    # A server-side database has no file to delete, so drop the schema instead
    # and let the app's own `db.connect()` rebuild it. Same promise as above:
    # the session starts empty. Without this, a second run against the same
    # Postgres inherits the first one's rows, and every test that counts a
    # user's workspaces starts failing for a reason that isn't its own.
    import asyncio

    async def _drop_schema() -> None:
        from api import db as _db
        from api import models as _m  # noqa: F401
        from api import telemetry as _t  # noqa: F401
        from api.conversation import embeddings as _e  # noqa: F401
        from api.conversation import models as _cm  # noqa: F401
        from api.documents import models as _dm  # noqa: F401
        from api.prompts import models as _pm  # noqa: F401

        async with _db.engine.begin() as conn:
            await conn.run_sync(_db.Base.metadata.drop_all)
        # Dispose before the tests start: this ran in a throwaway event loop,
        # and an asyncpg connection left in the pool is bound to that loop.
        await _db.engine.dispose()

    asyncio.run(_drop_schema())


import uuid

import pytest


def pytest_sessionfinish(session, exitstatus):
    """Keep the database only when there is a failure to inspect.

    The file is named per process so concurrent runs cannot collide, which
    would otherwise leave one behind for every run this repository has ever
    seen. A green run has nothing to post-mortem, so it cleans up after itself;
    a red one leaves the evidence exactly where the comment above promises.
    """
    if exitstatus == 0 and os.environ["DATABASE_URL"].startswith("sqlite"):
        try:
            Path.cwd().joinpath(_TEST_DB_NAME).unlink(missing_ok=True)
        except OSError:
            # Windows keeps a handle on an open SQLite file. Leaving a stray
            # database behind is not worth failing a green run over.
            pass


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


@pytest.fixture(autouse=True)
def _fresh_checkpointer():
    """Each test starts with an empty checkpoint store, like a fresh process.

    The graph checkpointer is a process-wide singleton now (a paused run is
    resumed by a later request, so a per-graph saver would be gone when it
    mattered). Production keys every run by a fresh uuid, but tests reuse fixed
    thread ids like "t-test" — so without this, one test's checkpoint is
    another's starting state and graph tests fail only when run together.
    """
    from api import checkpointing

    checkpointing._saver = None
    yield
    checkpointing._saver = None
