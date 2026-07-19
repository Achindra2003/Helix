"""The unauthenticated public-config endpoint and crash-reporting wiring (P4).

`/api/public-config` is the only endpoint that answers without a token, which
makes it the one place where a careless addition is readable by the entire
internet. The test that matters is therefore the negative one: that it returns
the notice and nothing else.
"""
import pytest
from fastapi.testclient import TestClient

from api import monitoring
from api.config import settings
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_public_config_needs_no_token(client):
    r = client.get("/api/public-config")
    assert r.status_code == 200


def test_public_config_exposes_only_the_notice(client):
    """A guard against future additions. If someone adds a field here, they
    have to come and change this test — which is the point, because the value
    they add is world-readable."""
    body = client.get("/api/public-config").json()
    assert set(body) == {"notice", "notice_link"}


def test_notice_is_empty_by_default(client):
    """Self-hosted is the default, and on your own instance a warning that your
    data may be wiped would simply be false."""
    assert client.get("/api/public-config").json()["notice"] == ""


def test_notice_is_served_when_set(client, monkeypatch):
    monkeypatch.setattr(settings, "public_notice", "Demo instance — data may be wiped.")
    assert (
        client.get("/api/public-config").json()["notice"]
        == "Demo instance — data may be wiped."
    )


def test_monitoring_is_off_without_a_dsn():
    """No DSN means no SDK and no network client — the self-hosted default."""
    assert monitoring.init_monitoring() is False


def test_monitoring_survives_a_broken_dsn(monkeypatch):
    """Monitoring that stops the app from booting has inverted its purpose."""
    monkeypatch.setattr(settings, "sentry_dsn", "not-a-valid-dsn")
    assert monitoring.init_monitoring() is False  # logged, not raised
