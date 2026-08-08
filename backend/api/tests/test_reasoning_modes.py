"""Reasoning mode chosen per run, rather than pinned instance-wide.

Five presets ship in `engine/ouroboros/presets.py`, each with its own depth,
energy curve, steer interval and four distinct prompts. The API used to pass
`settings.deep_reasoning_mode` — one `.env` string — at both call sites, so a
research group wanting Explore had to edit the server's environment, restart,
and change it for every workspace on the instance at once. It was the largest
built-and-unreachable capability in the product.

Mode is a property of the *question*, not of the team, so it is a per-run
argument. These tests pin the three things that could quietly go wrong: the
advertised list matching the engine, an unknown mode being refused rather than
silently becoming Analyze, and a paused run resuming in the mode it started in.
"""
import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.conversation.deep_reasoning import REASONING_MODES
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_advertised_modes_match_the_engines_presets():
    """The API declares this list so a cheap GET doesn't have to import
    LangGraph. This is what stops the two drifting apart."""
    from engine.ouroboros_bootstrap import load_ouroboros

    engine_modes = {m.value for m in load_ouroboros().models.Mode}
    assert set(REASONING_MODES) == engine_modes


def test_every_mode_is_described_for_a_human():
    """The picker shows these. A mode with no explanation of when to reach for
    it is a mode nobody reaches for."""
    for key, entry in REASONING_MODES.items():
        assert entry["label"], key
        assert len(entry["description"]) > 25, key


def test_modes_endpoint_lists_them_with_the_default(client):
    body = client.get("/conversations/deep/modes").json()
    assert {m["id"] for m in body["modes"]} == set(REASONING_MODES)
    assert body["default"] == settings.deep_reasoning_mode
    # The default has to be one of the offered options, or the UI cannot show
    # which one is selected.
    assert body["default"] in REASONING_MODES


def test_modes_endpoint_is_not_shadowed_by_the_branch_route(client):
    """`/conversations/deep/modes` sits under the same prefix as
    `/conversations/{conversation_id}/...`. If a variable route were declared
    first this would 404 or 422 instead."""
    assert client.get("/conversations/deep/modes").status_code == 200


def test_unknown_mode_is_refused(client, make_workspace):
    """The engine substitutes ANALYZE for anything it doesn't recognise, so
    without this a typo runs a different kind of reasoning and says nothing."""
    headers, _uid, ws_id = make_workspace(client)
    conv = client.post(
        "/conversations",
        json={"workspace_id": ws_id, "title": "t", "visibility": "shared"},
        headers=headers,
    )
    assert conv.status_code == 200, conv.text
    branch_id = conv.json()["branch_id"]

    r = client.post(
        f"/conversations/{branch_id}/deep",
        json={"prompt": "why", "mode": "explor"},  # one letter short
        headers=headers,
    )
    assert r.status_code == 400
    assert "explor" in r.json()["error"]["message"]


def test_resumable_row_carries_the_mode():
    """A paused Explore run must not come back as Analyze. The column defaults
    to "" so rows written before it existed still mean "instance default"."""
    from api.conversation.models import ResumableRunRow

    col = ResumableRunRow.__table__.c["mode"]
    assert col.default.arg == ""
