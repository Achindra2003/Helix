"""The seeded example workspace (P4).

conftest disables seeding for the rest of the suite; these switch it back on.

The tests worth having here are not "does a workspace exist" — they are the two
promises the feature makes: that the content actually exercises the features it
claims to demo, and that a broken seed never costs a user their account.
"""
import pytest
from fastapi.testclient import TestClient

from api import onboarding
from api.config import settings
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeding(monkeypatch):
    monkeypatch.setattr(settings, "seed_example_workspace", True)


def _register(client, email="seeded@test.dev"):
    r = client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _items(response):
    """List endpoints answer with an {"items": [...]} envelope (contract §1)."""
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _seeded_workspace(client, headers):
    workspaces = client.get("/api/workspaces", headers=headers).json()
    assert len(workspaces) == 1, workspaces
    return workspaces[0]


def _main_thread(client, headers, workspace_id):
    conversations = _items(
        client.get(f"/conversations?workspace_id={workspace_id}", headers=headers)
    )
    return next(c for c in conversations if c["title"] == "Choosing a database")


def test_new_user_lands_in_a_populated_workspace(client, seeding):
    """The whole point: not an empty screen on first load."""
    headers = _register(client, "populated@test.dev")

    workspace = _seeded_workspace(client, headers)
    assert workspace["name"] == onboarding.WORKSPACE_NAME

    conversations = _items(
        client.get(f"/conversations?workspace_id={workspace['id']}", headers=headers)
    )
    assert len(conversations) == 2  # the main thread and the one it references


def test_the_seeded_thread_is_actually_forked(client, seeding):
    """A fork is the product's headline claim, so the seed must contain a real
    one — two branches diverging from a shared node, not two separate threads."""
    headers = _register(client, "forked@test.dev")
    ws = _seeded_workspace(client, headers)
    main = _main_thread(client, headers, ws["id"])

    branches = _items(
        client.get(f"/conversations/{main['id']}/branches", headers=headers)
    )
    assert len(branches) == 2
    assert any(b["name"] == onboarding._FORK_NAME for b in branches)

    # The fork inherits the ancestor context and diverges from it: its history
    # starts with the main thread's opening turns, then differs.
    fork = next(b for b in branches if b["name"] == onboarding._FORK_NAME)
    root = next(b for b in branches if b["id"] != fork["id"])
    fork_history = client.get(
        f"/conversations/branches/{fork['id']}/history", headers=headers
    ).json()["nodes"]
    root_history = client.get(
        f"/conversations/branches/{root['id']}/history", headers=headers
    ).json()["nodes"]

    assert fork_history[0]["content"] == root_history[0]["content"]
    assert fork_history[-1]["content"] != root_history[-1]["content"]


def test_seeded_deep_run_matches_the_shape_real_runs_persist(client, seeding):
    """Guards the one place this module writes a row the store does not own.

    If run_log.py changes what it puts in `trace`, the replay UI will follow it
    and the seeded run would render wrong. Asserting the shape here means that
    change breaks a test instead of quietly producing a broken example.
    """
    headers = _register(client, "deeprun@test.dev")
    ws = _seeded_workspace(client, headers)
    main = _main_thread(client, headers, ws["id"])

    runs = _items(client.get(f"/conversations/{main['id']}/deep/runs", headers=headers))
    assert len(runs) == 1
    assert runs[0]["status"] == "done"
    assert runs[0]["stop_reason"] == "stability_threshold_reached"

    # The trace lives on the record endpoint — the replay view's source.
    record = client.get(
        f"/conversations/deep/runs/{runs[0]['id']}/record", headers=headers
    )
    assert record.status_code == 200, record.text
    trace = record.json()["trace"]
    assert set(trace) == {"steps", "stability_history", "steers"}
    assert [s["idx"] for s in trace["steps"]] == [0, 1, 2, 3]
    # Stability rises monotonically — a converging run, which is what the
    # replay's meter is meant to show.
    assert trace["stability_history"] == sorted(trace["stability_history"])


def test_seeded_document_is_ingested_and_retrievable(client, seeding):
    """Grounding needs a document that finished ingesting, not just a row."""
    headers = _register(client, "grounded@test.dev")
    ws = _seeded_workspace(client, headers)

    docs = _items(
        client.get(f"/api/workspaces/{ws['id']}/documents", headers=headers)
    )
    assert len(docs) == 1
    assert docs[0]["filename"] == onboarding._DOCUMENT_NAME
    assert docs[0]["status"] == "ready", docs[0]


def test_registration_survives_a_broken_seed(client, seeding, monkeypatch):
    """The rule this module is built around: demo content is never worth an
    account. If seeding raises, the user still gets registered and a token."""

    async def boom(*a, **kw):
        raise RuntimeError("seeding is broken")

    monkeypatch.setattr(onboarding, "_seed", boom)

    r = client.post(
        "/api/auth/register", json={"email": "survivor@test.dev", "password": "pw123456"}
    )
    assert r.status_code == 201
    assert r.json()["token"]


def test_seeding_can_be_turned_off(client, monkeypatch):
    monkeypatch.setattr(settings, "seed_example_workspace", False)
    headers = _register(client, "unseeded@test.dev")
    assert client.get("/api/workspaces", headers=headers).json() == []
