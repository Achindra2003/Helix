"""File grounding: extraction/chunking units, the ingest→search index, and the
HTTP surface — upload → ready → a chat turn grounded with citations.

The HTTP tests run ingestion inline (documents_ingest_inline) so status
transitions are deterministic; the embedder is the engine's shared one
(lexical fallback in hermetic runs — token overlap is exactly what the
relevance assertions rely on).
"""
import json

import pytest
from starlette.testclient import TestClient

import api.conversation.router as conv_router_mod
import api.documents.router as doc_router_mod
from api.config import settings
from api.conversation.store import InMemoryStore
from api.documents.service import chunk_text, extract_text
from api.main import app


# --- units: extraction + chunking ------------------------------------------------

def test_extract_plain_text_and_code():
    assert extract_text("notes.md", b"# Title\nBody") == "# Title\nBody"
    assert "def f" in extract_text("mod.py", b"def f():\n    return 1")


def test_extract_rejects_unsupported_binary():
    with pytest.raises(ValueError, match="unsupported"):
        extract_text("photo.png", b"\x89PNG....")


def test_extract_pdf():
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    # A blank PDF has no text: the clear error, not a silent empty document.
    with pytest.raises(ValueError, match="no extractable text"):
        extract_text("blank.pdf", buf.getvalue())


def test_chunks_overlap_so_boundary_facts_survive():
    words = [f"w{i}" for i in range(500)]
    chunks = chunk_text(" ".join(words), chunk_words=100, overlap=20)
    assert len(chunks) > 1
    first, second = chunks[0].split(), chunks[1].split()
    assert first[-20:] == second[:20]  # the overlap window
    assert " ".join(words) == " ".join(chunks[0].split() + [
        w for c in chunks[1:] for w in c.split()[20:]
    ])  # nothing lost


def test_short_text_is_one_chunk():
    assert chunk_text("just a few words") == ["just a few words"]


# --- HTTP: the knowledge-base lifecycle -------------------------------------------

SPEC = (
    "Helix retry policy specification. The provider seam retries transient "
    "failures exactly three times with exponential backoff. The circuit "
    "breaker threshold is four consecutive failures and the cooldown is "
    "thirty seconds. " + "Padding sentence about architecture. " * 120
)


@pytest.fixture(autouse=True)
def _inline_ingest(monkeypatch):
    monkeypatch.setattr(settings, "documents_ingest_inline", True)
    monkeypatch.setattr(conv_router_mod, "_store", InMemoryStore())


def _upload(client, headers, wid, filename="spec.md", content=SPEC):
    return client.post(
        f"/api/workspaces/{wid}/documents",
        files={"file": (filename, content.encode(), "text/markdown")},
        headers=headers,
    )


def test_upload_ingests_and_lists(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        up = _upload(client, headers, wid)
        assert up.status_code == 200, up.text
        doc = up.json()
        assert doc["status"] == "ready"
        assert doc["chunk_count"] >= 1
        assert doc["text_chars"] > 100

        listed = client.get(
            f"/api/workspaces/{wid}/documents", headers=headers
        ).json()["items"]
        assert [d["id"] for d in listed] == [doc["id"]]


def test_bad_file_lands_as_error_status_not_500(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        up = _upload(client, headers, wid, filename="img.png", content="binaryish")
        assert up.status_code == 200
        assert up.json()["status"] == "error"
        assert "unsupported" in up.json()["error"]


def test_search_finds_the_relevant_chunk(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        _upload(client, headers, wid)
        _upload(client, headers, wid, filename="other.md",
                content="Deployment calendar and holiday schedule. " * 50)

        hits = client.post(
            f"/api/workspaces/{wid}/documents/search",
            json={"query": "how many times does the retry policy retry?"},
            headers=headers,
        ).json()["items"]
        assert hits, "expected at least one hit"
        assert hits[0]["filename"] == "spec.md"
        assert "three times" in hits[0]["content"]
        assert hits[0]["score"] > 0


def test_chat_turn_is_grounded_with_citations(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        _upload(client, headers, wid)

        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t"},
            headers=headers,
        ).json()
        resp = client.post(
            f"/conversations/{conv['branch_id']}/messages",
            json={"prompt": "what is the retry policy retry count?"},
            headers=headers,
        )
        assert resp.status_code == 200
        frames = [
            json.loads(line[len("data: "):])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        grounding = [f for f in frames if f["kind"] == "grounding"]
        assert grounding, "expected a grounding frame before the reply"
        items = grounding[0]["items"]
        assert items[0]["filename"] == "spec.md"
        assert {"document_id", "chunk_index", "score", "excerpt"} <= set(items[0])


def test_unrelated_question_gets_no_grounding(make_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        _upload(client, headers, wid)

        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t"},
            headers=headers,
        ).json()
        resp = client.post(
            f"/conversations/{conv['branch_id']}/messages",
            json={"prompt": "xylophone quokka zeppelin"},
            headers=headers,
        )
        frames = [
            json.loads(line[len("data: "):])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        assert not [f for f in frames if f["kind"] == "grounding"]


def test_rbac_upload_delete_and_isolation(make_workspace, make_user, join_workspace):
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        doc = _upload(client, headers, wid).json()

        # An observer may read but not upload.
        obs_headers, _ = join_workspace(client, headers, wid, role="observer")
        assert (
            client.get(f"/api/workspaces/{wid}/documents", headers=obs_headers)
        ).status_code == 200
        assert _upload(client, obs_headers, wid).status_code == 403

        # A collaborator can't delete someone else's upload; the owner can.
        collab_headers, _ = join_workspace(client, headers, wid)
        assert (
            client.delete(
                f"/api/workspaces/{wid}/documents/{doc['id']}", headers=collab_headers
            )
        ).status_code == 403
        assert (
            client.delete(
                f"/api/workspaces/{wid}/documents/{doc['id']}", headers=headers
            )
        ).status_code == 200

        # A non-member sees nothing at all.
        outsider, _ = make_user(client)
        assert (
            client.get(f"/api/workspaces/{wid}/documents", headers=outsider)
        ).status_code == 404


def test_oversize_upload_is_413(make_workspace, monkeypatch):
    monkeypatch.setattr(settings, "document_max_bytes", 100)
    with TestClient(app) as client:
        headers, _, wid = make_workspace(client)
        assert _upload(client, headers, wid).status_code == 413
