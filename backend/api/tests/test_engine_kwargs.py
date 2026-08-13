"""How the engine is configured against a Postgres that goes to sleep.

The hosted instance runs on a serverless Postgres (Neon), whose compute
suspends after a few minutes idle and takes every pooled connection with it.
On 13 August that produced an outage with no application error in it at all:
`/health` failed inside `db_ping`, in `asyncpg.connect`, with a bare
`TimeoutError`, while the process itself was healthy and had memory to spare.

`pool_pre_ping` is the setting that turns that from an error into a reconnect,
and it was absent. These pin it, and pin the two things about it that are easy
to break later:

  - it must apply to *every* Postgres URL, not only the pooled ones. The
    original code only ever branched on `db_pooled`, and adding a second
    Postgres branch above it is precisely where a merge can go wrong.
  - `connect_args` is now written twice — once for the connect timeout, once
    for the transaction-pooler caches — and the second must merge into the
    first rather than replace it. Losing `statement_cache_size` there would
    silently reintroduce the `prepared statement "__asyncpg_stmt_N__" does not
    exist` bug that `_engine_kwargs` was originally written to prevent, and it
    would only appear under concurrency, in production.
"""
import pytest

from api import db
from api.config import settings


@pytest.fixture
def pg_url(monkeypatch):
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://u:p@example.neon.tech/db"
    )


def test_sqlite_is_left_alone():
    """The dev database neither suspends nor pools; nothing should be added."""
    monkey = settings.database_url
    assert monkey.startswith("sqlite"), "this test assumes the SQLite dev default"
    kwargs = db._engine_kwargs()
    assert "pool_pre_ping" not in kwargs
    assert "connect_args" not in kwargs


def test_postgres_gets_pre_ping_and_a_bounded_connect(pg_url):
    kwargs = db._engine_kwargs()
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] > 0
    # A wake that takes longer than this should fail the request, not hold a
    # worker until the platform's own health check gives up on the process.
    assert 0 < kwargs["connect_args"]["timeout"] <= 30


def test_pre_ping_applies_without_the_pooler(pg_url, monkeypatch):
    monkeypatch.setattr(settings, "db_pooled", False)
    assert db._engine_kwargs()["pool_pre_ping"] is True


def test_pooler_caches_are_disabled_without_losing_the_timeout(pg_url, monkeypatch):
    """Both connect_args writes must survive each other."""
    monkeypatch.setattr(settings, "db_pooled", True)
    kwargs = db._engine_kwargs()
    assert kwargs["connect_args"]["statement_cache_size"] == 0
    assert kwargs["prepared_statement_cache_size"] == 0
    assert "timeout" in kwargs["connect_args"], (
        "the pooler branch replaced connect_args instead of merging into it"
    )
