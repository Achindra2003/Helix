"""Turning a filename into a reference.

`[smith-et-al-final-v3.pdf — part 4]` names a file on somebody's laptop, not a
work another person can find. These cover the four optional fields that fix
that, and the single rule — `cite_as` — that keeps the chip, the export and the
model's own context from naming the same source three different ways.
"""
import pytest
from starlette.testclient import TestClient

from api.documents.models import DocumentRow, cite_as
from api.main import app


def _upload(client, headers, wid, name="attention.pdf", body=b"transformers are a thing"):
    resp = client.post(
        f"/api/workspaces/{wid}/documents",
        files={"file": (name, body, "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _row(**kw):
    return DocumentRow(filename=kw.pop("filename", "f.pdf"), **kw)


@pytest.mark.parametrize(
    "fields,expected",
    [
        ({"authors": "Vaswani et al.", "year": "2017"}, "Vaswani et al. (2017)"),
        ({"authors": "Vaswani et al."}, "Vaswani et al."),
        ({"doc_title": "Attention Is All You Need", "year": "2017"},
         "Attention Is All You Need (2017)"),
        ({"doc_title": "Attention Is All You Need"}, "Attention Is All You Need"),
        # Nothing catalogued: the filename is at least true. A source with no
        # visible name reads as a rendering fault.
        ({}, "f.pdf"),
    ],
)
def test_cite_as_degrades_to_something_true(fields, expected):
    assert cite_as(_row(**fields)) == expected


def test_metadata_round_trips(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        doc = _upload(client, headers, wid)
        assert doc["cite_as"] == "attention.pdf", "uncatalogued falls back to the file"

        resp = client.patch(
            f"/api/workspaces/{wid}/documents/{doc['id']}",
            json={
                "authors": "Vaswani et al.",
                "year": "2017",
                "doc_title": "Attention Is All You Need",
                "identifier": "arXiv:1706.03762",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["cite_as"] == "Vaswani et al. (2017)"

        listed = client.get(f"/api/workspaces/{wid}/documents", headers=headers).json()
        assert listed["items"][0]["identifier"] == "arXiv:1706.03762"


def test_a_partial_record_beats_an_empty_one(make_workspace):
    """Someone adding a year six weeks later must not have to retype the
    authors — omitted fields are left alone rather than cleared."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        doc = _upload(client, headers, wid)

        client.patch(
            f"/api/workspaces/{wid}/documents/{doc['id']}",
            json={"authors": "Vaswani et al."},
            headers=headers,
        )
        resp = client.patch(
            f"/api/workspaces/{wid}/documents/{doc['id']}",
            json={"year": "2017"},
            headers=headers,
        )
        assert resp.json()["cite_as"] == "Vaswani et al. (2017)"


def test_any_collaborator_may_catalogue(make_workspace, join_workspace):
    """Cataloguing is exactly the work a second person does well. Describing is
    not destroying — deletion stays uploader-or-owner."""
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        mate_headers, _ = join_workspace(client, headers, wid, role="collaborator")
        doc = _upload(client, headers, wid)

        resp = client.patch(
            f"/api/workspaces/{wid}/documents/{doc['id']}",
            json={"authors": "someone else"},
            headers=mate_headers,
        )
        assert resp.status_code == 200

        # …but they still cannot delete a document they did not upload.
        assert client.delete(
            f"/api/workspaces/{wid}/documents/{doc['id']}", headers=mate_headers
        ).status_code == 403


def test_observers_cannot_catalogue(make_workspace, join_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        obs_headers, _ = join_workspace(client, headers, wid, role="observer")
        doc = _upload(client, headers, wid)

        resp = client.patch(
            f"/api/workspaces/{wid}/documents/{doc['id']}",
            json={"authors": "x"},
            headers=obs_headers,
        )
        assert resp.status_code == 403


def test_non_members_get_404_not_403(make_workspace, make_user):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        doc = _upload(client, headers, wid)
        outsider = make_user(client)[0]

        resp = client.patch(
            f"/api/workspaces/{wid}/documents/{doc['id']}",
            json={"authors": "x"},
            headers=outsider,
        )
        assert resp.status_code == 404
