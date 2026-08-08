"""Addressing a person, and the notice that outlives the tab.

Helix could talk *to a room* — a note is a message the model never reads, so
two people in a thread can actually speak. It could not address anyone. There
was no way to write "Priya, is this the number you meant?" and have Priya find
out; presence said who was there, and nothing said "come and look".

The tests that matter here are the ones about who gets told, because a mention
system's failures are all social: telling the wrong person, telling nobody
silently, or telling someone about a thread they cannot open.
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _thread(client, headers, ws_id, visibility="shared"):
    r = client.post(
        "/conversations",
        json={"workspace_id": ws_id, "title": "t", "visibility": visibility},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["branch_id"]


def _note(client, headers, branch_id, text):
    r = client.post(
        f"/conversations/{branch_id}/notes", json={"content": text}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()


def _notices(client, headers):
    r = client.get("/api/notices", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["notices"]


def test_a_mention_reaches_the_person_named(client, make_workspace, join_workspace):
    owner_headers, _oid, ws_id = make_workspace(client)
    mate_headers, _mid = join_workspace(client, owner_headers, ws_id)
    mate_email = client.get("/api/me", headers=mate_headers).json()["email"]
    handle = mate_email.split("@")[0]

    branch = _thread(client, owner_headers, ws_id)
    _note(client, owner_headers, branch, f"@{handle} is this the number you meant?")

    got = _notices(client, mate_headers)
    assert len(got) == 1
    assert got[0]["kind"] == "mention"
    assert handle in got[0]["excerpt"]
    assert got[0]["branch_id"] == branch
    assert got[0]["read"] is False


def test_it_reaches_nobody_else(client, make_workspace, join_workspace):
    """A mention that quietly reached the wrong person would be worse than one
    that reached no one."""
    owner_headers, _oid, ws_id = make_workspace(client)
    mate_headers, _mid = join_workspace(client, owner_headers, ws_id)
    bystander_headers, _bid = join_workspace(client, owner_headers, ws_id)
    mate_handle = client.get("/api/me", headers=mate_headers).json()["email"].split("@")[0]

    branch = _thread(client, owner_headers, ws_id)
    _note(client, owner_headers, branch, f"@{mate_handle} have a look")

    assert len(_notices(client, mate_headers)) == 1
    assert _notices(client, bystander_headers) == []


def test_mentioning_yourself_is_signing_not_asking(client, make_workspace):
    owner_headers, _oid, ws_id = make_workspace(client)
    me = client.get("/api/me", headers=owner_headers).json()["email"].split("@")[0]

    branch = _thread(client, owner_headers, ws_id)
    _note(client, owner_headers, branch, f"@{me} will pick this up tomorrow")

    assert _notices(client, owner_headers) == []


def test_an_unknown_handle_notifies_nobody_and_still_posts(client, make_workspace):
    """Silence is the correct failure: the note is still said, and the author
    can see their own words to notice the name did not take."""
    owner_headers, _oid, ws_id = make_workspace(client)
    branch = _thread(client, owner_headers, ws_id)

    node = _note(client, owner_headers, branch, "@nobody_at_all please look")

    assert node["content"] == "@nobody_at_all please look"
    assert _notices(client, owner_headers) == []


def test_a_private_thread_does_not_summon_anyone(client, make_workspace, join_workspace):
    """A notice pointing at a thread the reader cannot open is a dead end, so
    mentions resolve only where the recipient can actually follow the link."""
    owner_headers, _oid, ws_id = make_workspace(client)
    mate_headers, _mid = join_workspace(client, owner_headers, ws_id)
    handle = client.get("/api/me", headers=mate_headers).json()["email"].split("@")[0]

    branch = _thread(client, owner_headers, ws_id, visibility="private")
    _note(client, owner_headers, branch, f"@{handle} look at this")

    assert _notices(client, mate_headers) == []


def test_someone_outside_the_workspace_is_not_reachable(
    client, make_workspace, make_user
):
    owner_headers, _oid, ws_id = make_workspace(client)
    outsider_headers, _uid = make_user(client)
    handle = client.get("/api/me", headers=outsider_headers).json()["email"].split("@")[0]

    branch = _thread(client, owner_headers, ws_id)
    _note(client, owner_headers, branch, f"@{handle} you should see this")

    assert _notices(client, outsider_headers) == []


def test_two_names_in_one_note_are_two_notices(client, make_workspace, join_workspace):
    owner_headers, _oid, ws_id = make_workspace(client)
    a_headers, _a = join_workspace(client, owner_headers, ws_id)
    b_headers, _b = join_workspace(client, owner_headers, ws_id)
    a = client.get("/api/me", headers=a_headers).json()["email"].split("@")[0]
    b = client.get("/api/me", headers=b_headers).json()["email"].split("@")[0]

    branch = _thread(client, owner_headers, ws_id)
    _note(client, owner_headers, branch, f"@{a} and @{b} — which of you owns this?")

    assert len(_notices(client, a_headers)) == 1
    assert len(_notices(client, b_headers)) == 1


def test_a_notice_survives_and_can_be_marked_seen(
    client, make_workspace, join_workspace
):
    """The whole point of the table: the bell used to be page memory."""
    owner_headers, _oid, ws_id = make_workspace(client)
    mate_headers, _mid = join_workspace(client, owner_headers, ws_id)
    handle = client.get("/api/me", headers=mate_headers).json()["email"].split("@")[0]

    branch = _thread(client, owner_headers, ws_id)
    _note(client, owner_headers, branch, f"@{handle} ping")

    assert _notices(client, mate_headers)[0]["read"] is False
    assert client.post("/api/notices/read", headers=mate_headers).status_code == 200

    after = _notices(client, mate_headers)
    assert len(after) == 1, "read is not deleted — it is still the record"
    assert after[0]["read"] is True


def test_marking_read_is_yours_alone(client, make_workspace, join_workspace):
    owner_headers, _oid, ws_id = make_workspace(client)
    a_headers, _a = join_workspace(client, owner_headers, ws_id)
    b_headers, _b = join_workspace(client, owner_headers, ws_id)
    a = client.get("/api/me", headers=a_headers).json()["email"].split("@")[0]
    b = client.get("/api/me", headers=b_headers).json()["email"].split("@")[0]

    branch = _thread(client, owner_headers, ws_id)
    _note(client, owner_headers, branch, f"@{a} @{b} both of you")

    client.post("/api/notices/read", headers=a_headers)

    assert _notices(client, a_headers)[0]["read"] is True
    assert _notices(client, b_headers)[0]["read"] is False


def test_notices_need_a_session(client):
    assert client.get("/api/notices").status_code in (401, 403)
    assert client.post("/api/notices/read").status_code in (401, 403)
