"""Rate limiting (P2).

conftest disables the limiter for the rest of the suite, so these tests switch
it back on deliberately. `rate_limit.reset()` runs around each one — the
counters are process-global, and a leaked bucket would make an unrelated test
fail later in a way that looks like a real bug.
"""
import pytest
from fastapi.testclient import TestClient

from api import rate_limit
from api.config import settings
from api.main import app
from api.rate_limit import _Window, limit_for


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_counters():
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.fixture
def limits(monkeypatch):
    """Enable the limiter and set specific budgets for one test."""

    def _set(**values):
        monkeypatch.setattr(settings, "rate_limit_enabled", True)
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)

    return _set


# --- the window itself (pure, no HTTP) ---------------------------------------


def test_window_allows_up_to_the_limit_then_refuses():
    w = _Window("t", limit=3, window_s=60.0)
    assert [w.hit("bob", now=100.0) for _ in range(3)] == [None, None, None]
    assert w.hit("bob", now=100.0) is not None


def test_window_reports_when_to_retry():
    w = _Window("t", limit=1, window_s=60.0)
    w.hit("bob", now=100.0)
    wait = w.hit("bob", now=110.0)
    assert wait == pytest.approx(50.0)  # 60s window, 10s elapsed


def test_window_frees_up_as_events_age_out():
    """Sliding, not fixed: an old event stops counting once it leaves the
    window, rather than everyone resetting together on a clock boundary."""
    w = _Window("t", limit=1, window_s=60.0)
    assert w.hit("bob", now=100.0) is None
    assert w.hit("bob", now=130.0) is not None
    assert w.hit("bob", now=161.0) is None


def test_identities_do_not_share_a_budget():
    w = _Window("t", limit=1, window_s=60.0)
    assert w.hit("alice", now=100.0) is None
    assert w.hit("bob", now=100.0) is None


def test_idle_identities_are_reclaimed(monkeypatch):
    """Memory must not grow with every address ever seen.

    `hit` only runs for identities that are currently sending, so it cannot
    reclaim one that fired once and never came back — an attacker cycling
    through addresses would pin an entry each. The periodic sweep is what
    bounds it, so this asserts on the bucket itself, not on behaviour.
    """
    monkeypatch.setattr(rate_limit, "_SWEEP_EVERY", 10)
    # A high limit so every call below is admitted: only admitted events tick
    # the sweep counter, and a refused one must not.
    w = _Window("t", limit=50, window_s=60.0)

    for i in range(30):  # 30 one-shot identities, none of which return
        w.hit(f"drive-by-{i}", now=100.0)
    assert len(rate_limit._hits["t"]) == 30  # all still inside the window

    # Long after the window has passed, one active identity keeps calling. Its
    # traffic is what drives the sweep that clears the thirty stale entries.
    for _ in range(10):
        w.hit("regular", now=500.0)
    assert set(rate_limit._hits["t"]) == {"regular"}


def test_zero_limit_disables_the_window():
    w = _Window("t", limit=0, window_s=60.0)
    assert all(w.hit("bob", now=100.0) is None for _ in range(50))


# --- which routes are limited -------------------------------------------------


def test_only_mutating_methods_are_limited(limits):
    """Reads are cheap and constant; throttling them would break the UI's
    polling without protecting anything."""
    limits()
    assert limit_for("GET", "/api/auth/login") is None
    assert limit_for("POST", "/api/auth/login") is not None


def test_route_classes_get_their_own_budgets(limits):
    limits()
    assert limit_for("POST", "/api/auth/register").name == "auth"
    assert limit_for("POST", "/conversations/b1/messages").name == "messages"
    assert limit_for("POST", "/conversations/b1/deep").name == "runs"
    assert limit_for("POST", "/conversations/b1/agent").name == "runs"
    # Uploads: heaviest write in the app, and rejected files still cost a row
    # because the extension allowlist runs after the document row is committed.
    assert limit_for("POST", "/api/workspaces/w1/documents").name == "uploads"
    # Unrelated writes stay unlimited — including the workspace route that the
    # upload path is a prefix of, which a sloppier match would have caught.
    assert limit_for("POST", "/api/workspaces") is None
    assert limit_for("POST", "/api/workspaces/w1/settings/tools") is None


def test_master_switch_turns_everything_off(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    assert limit_for("POST", "/api/auth/register") is None


# --- end to end through the app ----------------------------------------------


def test_signup_flood_is_refused_with_429_and_retry_after(client, limits):
    limits(rate_limit_auth_per_hour=3)

    for i in range(3):
        ok = client.post(
            "/api/auth/register",
            json={"email": f"flood{i}@test.dev", "password": "pw123456"},
        )
        assert ok.status_code == 201, ok.text

    blocked = client.post(
        "/api/auth/register",
        json={"email": "one-too-many@test.dev", "password": "pw123456"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    # Actionable, not a mystery: the client is told when to come back.
    assert int(blocked.headers["Retry-After"]) >= 1


def test_login_guessing_shares_the_auth_budget(client, limits):
    """Registration and login draw on one bucket, so an attacker cannot spend
    the signup budget and then guess passwords freely."""
    limits(rate_limit_auth_per_hour=2)

    client.post(
        "/api/auth/register", json={"email": "real@test.dev", "password": "pw123456"}
    )
    client.post(
        "/api/auth/login", json={"email": "real@test.dev", "password": "wrong-guess"}
    )
    third = client.post(
        "/api/auth/login", json={"email": "real@test.dev", "password": "wrong-again"}
    )
    assert third.status_code == 429


def test_limiting_happens_before_the_body_size_check(client, limits):
    """Otherwise an attacker gets unlimited attempts by making each one
    oversized: the 413 would fire first and the attempt would never be
    counted."""
    limits(rate_limit_auth_per_hour=1)
    huge = {"email": "a@test.dev", "password": "x" * 100_000}

    client.post("/api/auth/register", json=huge)
    second = client.post("/api/auth/register", json=huge)

    assert second.status_code == 429  # not 413


def test_authenticated_users_are_charged_separately(client, limits, make_user):
    """Two teammates on one office IP must not throttle each other."""
    limits(rate_limit_messages_per_minute=1)
    alice_headers, _ = make_user(client)
    bob_headers, _ = make_user(client)

    body = {"prompt": "hello"}
    client.post("/conversations/nope/messages", json=body, headers=alice_headers)
    alice_second = client.post("/conversations/nope/messages", json=body, headers=alice_headers)
    bob_first = client.post("/conversations/nope/messages", json=body, headers=bob_headers)

    assert alice_second.status_code == 429
    assert bob_first.status_code != 429
