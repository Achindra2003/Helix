"""What a workspace card is allowed to say about a workspace.

`GET /api/workspaces` used to return a name, a role and two ids, so the picker
could only draw a shelf of plates that differed by name — you opened each one to
find out which was which. It now carries how many threads the caller can open
and how many people are in the room.

The interesting half is the *caller* qualifier. A private conversation is
private: counting somebody else's into a number shown on a card would tell you
it exists, which is exactly what private visibility promises not to do. So the
count is "threads you may open", not "threads that exist", and these tests pin
that difference rather than the arithmetic.
"""


import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _conv(client, headers, ws_id, title, visibility):
    r = client.post(
        "/conversations",
        json={"workspace_id": ws_id, "title": title, "visibility": visibility},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _ws(client, headers, ws_id):
    r = client.get("/api/workspaces", headers=headers)
    assert r.status_code == 200, r.text
    return next(w for w in r.json() if w["id"] == ws_id)


def test_a_new_workspace_reports_itself_as_empty(client, make_workspace):
    headers, _uid, ws_id = make_workspace(client)

    w = _ws(client, headers, ws_id)
    assert w["conversation_count"] == 0
    assert w["member_count"] == 1


def test_counts_follow_the_threads_and_the_people(client, make_workspace, join_workspace):
    headers, _uid, ws_id = make_workspace(client)
    _conv(client, headers, ws_id, "one", "shared")
    _conv(client, headers, ws_id, "two", "shared")
    join_workspace(client, headers, ws_id)

    w = _ws(client, headers, ws_id)
    assert w["conversation_count"] == 2
    assert w["member_count"] == 2


def test_a_teammates_private_thread_is_not_counted_for_you(
    client, make_workspace, join_workspace
):
    """The whole point of the qualifier: a number that moved when a teammate
    started a private thread would announce the thread."""
    owner_headers, _uid, ws_id = make_workspace(client)
    mate_headers, _mate_id = join_workspace(client, owner_headers, ws_id)

    _conv(client, mate_headers, ws_id, "mine alone", "private")

    assert _ws(client, owner_headers, ws_id)["conversation_count"] == 0
    # ...and its author still sees it, or the count would be useless to them.
    assert _ws(client, mate_headers, ws_id)["conversation_count"] == 1


def test_a_shared_thread_counts_for_everyone(client, make_workspace, join_workspace):
    owner_headers, _uid, ws_id = make_workspace(client)
    mate_headers, _mate_id = join_workspace(client, owner_headers, ws_id)

    _conv(client, owner_headers, ws_id, "the room's thread", "shared")

    assert _ws(client, owner_headers, ws_id)["conversation_count"] == 1
    assert _ws(client, mate_headers, ws_id)["conversation_count"] == 1


def test_the_counts_do_not_leak_across_workspaces(client, make_workspace):
    headers, _uid, first = make_workspace(client)
    second = client.post(
        "/api/workspaces", json={"name": "second"}, headers=headers
    ).json()["id"]
    _conv(client, headers, first, "only here", "shared")

    assert _ws(client, headers, first)["conversation_count"] == 1
    assert _ws(client, headers, second)["conversation_count"] == 0
