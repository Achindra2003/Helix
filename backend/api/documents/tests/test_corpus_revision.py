"""Retrieval caches an index; these are the ways that cache could go wrong.

The index (vectors as one matrix, BM25's postings) is built once and reused
until the workspace's corpus revision changes — which turned a 1.28 s grounded
send at 10,000 chunks into 7 ms. The whole correctness of that rests on one
invariant: **anything that changes the chunk set bumps the revision.**

Miss it and the failure is silent and bad in both directions — a document you
just uploaded never grounds anything, or a document you deleted keeps being
cited. So these test through the HTTP surface, on behaviour a person would
notice, rather than asserting that a counter moved.
"""
import pytest
from starlette.testclient import TestClient

from api.main import app


def _upload(client, headers, wid, name, body):
    resp = client.post(
        f"/api/workspaces/{wid}/documents",
        files={"file": (name, body, "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _search(client, headers, wid, query):
    resp = client.post(
        f"/api/workspaces/{wid}/documents/search",
        json={"query": query, "k": 6},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


@pytest.fixture
def client(monkeypatch):
    # Ingestion is fire-and-forget in production (the upload response must not
    # wait on embedding). Inline here so "upload, then search" is a fact rather
    # than a race — the thing under test is cache invalidation, not scheduling.
    from api.config import settings

    monkeypatch.setattr(settings, "documents_ingest_inline", True)
    with TestClient(app) as c:
        yield c


PAPER = (
    "The escalation policy routes a ZX-9931 alarm to the on-call engineer "
    "within ninety seconds, and pages the secondary after five minutes."
)
SECOND = (
    "The rollback runbook restores the previous container image and replays "
    "the write-ahead log from the last checkpoint."
)


def test_a_new_document_is_searchable_immediately(client, make_workspace):
    """The first half of the invariant. A cached empty index must not outlive
    the upload that filled it — "I uploaded it and it found nothing" is the
    complaint this prevents."""
    headers, _, wid = make_workspace(client)

    # Warm the cache on an empty workspace first: this is the ordering that
    # actually breaks, and it is the normal one (people search, then upload).
    assert _search(client, headers, wid, "ZX-9931 escalation") == []

    _upload(client, headers, wid, "policy.txt", PAPER)
    hits = _search(client, headers, wid, "ZX-9931 escalation")
    assert hits, "a document uploaded after a search never became searchable"
    assert "ZX-9931" in hits[0]["content"]


def test_a_deleted_document_stops_grounding_at_once(client, make_workspace):
    """The other half, and the one with teeth: a document removed from the
    knowledge base must stop being quoted into prompts on the next send, not
    whenever something else happens to change the corpus."""
    headers, _, wid = make_workspace(client)
    doc = _upload(client, headers, wid, "policy.txt", PAPER)
    assert _search(client, headers, wid, "ZX-9931 escalation")

    resp = client.delete(
        f"/api/workspaces/{wid}/documents/{doc['id']}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert _search(client, headers, wid, "ZX-9931 escalation") == [], (
        "a deleted document was still being retrieved from a stale index"
    )


def test_a_second_document_joins_the_index(client, make_workspace):
    """Adding to a warm corpus, not just to an empty one — the cache is keyed
    per workspace and rebuilt wholesale, so this is where an off-by-one in the
    revision check would show."""
    headers, _, wid = make_workspace(client)
    _upload(client, headers, wid, "policy.txt", PAPER)
    assert _search(client, headers, wid, "rollback runbook checkpoint") == []

    _upload(client, headers, wid, "runbook.txt", SECOND)
    assert _search(client, headers, wid, "rollback runbook checkpoint")
    # And the first document is still there: a rebuild must not lose rows.
    assert _search(client, headers, wid, "ZX-9931 escalation")


def test_re_uploading_replaces_rather_than_duplicates(client, make_workspace):
    """`ingest` deletes a document's old chunks before writing new ones. If the
    revision did not move, the index would keep serving chunks whose rows no
    longer exist."""
    headers, _, wid = make_workspace(client)
    _upload(client, headers, wid, "policy.txt", PAPER)
    before = _search(client, headers, wid, "ZX-9931 escalation")
    assert before

    # Same filename, different content — a second document, and the corpus
    # now holds both.
    _upload(client, headers, wid, "policy.txt", SECOND)
    assert _search(client, headers, wid, "rollback runbook checkpoint")


def test_one_workspaces_documents_never_reach_another(client, make_workspace):
    """The cache is per workspace and so is the corpus revision. A shared
    counter, or a cache keyed on anything coarser, would leak a team's papers
    into another team's answers — the worst bug this file could miss."""
    headers, _, wid_a = make_workspace(client)
    _upload(client, headers, wid_a, "policy.txt", PAPER)

    other_headers, _, wid_b = make_workspace(client)
    assert _search(client, other_headers, wid_b, "ZX-9931 escalation") == []
