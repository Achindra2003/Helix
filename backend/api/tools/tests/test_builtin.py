"""The built-in catalog: allowlist resolution, binding policy, and handlers.

Handlers run against fake retrieval substrates — what's under test is the
tool layer's own behaviour (result rendering, honest emptiness, caps,
availability), not retrieval quality (that's the golden-set harness).
"""
from api.tools import DEFAULT_ALLOWED, bindable, openai_schema, resolve_allowlist
from api.tools.builtin import (
    make_tools,
    render_conversation_hits,
    render_document_hits,
    render_web_results,
)


# --- allowlist resolution ----------------------------------------------------


def test_allowlist_defaults_are_workspace_internal_only():
    assert resolve_allowlist(None) == list(DEFAULT_ALLOWED)
    assert resolve_allowlist("") == list(DEFAULT_ALLOWED)
    assert "web_search" not in resolve_allowlist(None)


def test_allowlist_garbage_falls_back_to_default():
    assert resolve_allowlist("not json{") == list(DEFAULT_ALLOWED)
    assert resolve_allowlist('{"a": 1}') == list(DEFAULT_ALLOWED)


def test_allowlist_explicit_empty_stays_empty():
    """"[]" is the owner saying "no tools" — not "give me the default"."""
    assert resolve_allowlist("[]") == []


def test_allowlist_roundtrip():
    assert resolve_allowlist('["web_search"]') == ["web_search"]


def test_bindable_filters_unallowed_and_unavailable():
    tools = make_tools(
        workspace_id="w", viewer_id="u", documents=None, embeddings=None,
        tavily_key="",  # web_search exists but is unavailable
    )
    names = {t.name for t in tools}
    assert names == {"search_knowledge_base", "search_conversations", "web_search"}

    # Even if the owner allows web_search, no key ⇒ never bound.
    bound = bindable(tools, ["search_knowledge_base", "web_search"])
    assert [t.name for t in bound] == ["search_knowledge_base"]

    with_key = make_tools(
        workspace_id="w", viewer_id="u", documents=None, embeddings=None,
        tavily_key="tvly-x",
    )
    bound = bindable(with_key, ["search_knowledge_base", "web_search"])
    assert {t.name for t in bound} == {"search_knowledge_base", "web_search"}


def test_web_search_is_sensitive_and_schema_shape_is_openai():
    (web,) = [
        t for t in make_tools(
            workspace_id="w", viewer_id="u", documents=None, embeddings=None,
            tavily_key="k",
        )
        if t.name == "web_search"
    ]
    assert web.sensitive and web.available
    schema = openai_schema(web)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "web_search"
    assert schema["function"]["parameters"]["required"] == ["query"]


# --- handlers ----------------------------------------------------------------


class _FakeDocuments:
    def __init__(self, hits):
        self._hits = hits
        self.queries = []

    async def search(self, workspace_id, query, *, k=None, **kw):
        self.queries.append((workspace_id, query))
        return self._hits


class _FakeEmbeddings:
    def __init__(self, items):
        self._items = items
        self.calls = []

    async def search_workspace(self, workspace_id, viewer_id, query, *, k=10, **kw):
        self.calls.append((workspace_id, viewer_id, query))
        return self._items


async def test_search_knowledge_base_renders_hits_with_identity():
    docs = _FakeDocuments(
        [
            {
                "document_id": "d1", "filename": "runbook.md", "chunk_index": 2,
                "score": 0.61, "content": "Rollback: swap the router back.",
            }
        ]
    )
    (kb,) = [
        t for t in make_tools(
            workspace_id="w1", viewer_id="u1", documents=docs, embeddings=None,
        )
        if t.name == "search_knowledge_base"
    ]
    out = await kb.handler(query="how do we roll back?")
    assert "runbook.md" in out and "part 3" in out and "swap the router" in out
    assert docs.queries == [("w1", "how do we roll back?")]


async def test_search_conversations_runs_as_the_viewer():
    """The viewer's identity flows into visibility filtering — the agent
    can't read a private thread its user couldn't open."""
    emb = _FakeEmbeddings(
        [
            {
                "node_id": "n1", "conversation_id": "c1",
                "conversation_title": "Launch plan", "branch_id": "b1",
                "role": "assistant", "excerpt": "we decided Tuesday",
                "score": 0.44, "author_id": "u2", "created_at": "2026-07-01T00:00:00",
            }
        ]
    )
    (conv,) = [
        t for t in make_tools(
            workspace_id="w1", viewer_id="viewer-9", documents=None, embeddings=emb,
        )
        if t.name == "search_conversations"
    ]
    out = await conv.handler(query="when do we launch")
    assert "Launch plan" in out and "we decided Tuesday" in out
    assert emb.calls == [("w1", "viewer-9", "when do we launch")]


async def test_empty_results_are_an_answer_not_an_error():
    assert "No relevant documents" in render_document_hits([])
    assert "No relevant messages" in render_conversation_hits([])
    assert "no results" in render_web_results({})


def test_web_results_render_answer_and_sources():
    out = render_web_results(
        {
            "answer": "Python 3.13 is current.",
            "results": [
                {"title": "python.org", "url": "https://python.org", "content": "Download 3.13"}
            ],
        }
    )
    assert "Python 3.13 is current." in out
    assert "python.org" in out and "https://python.org" in out


def test_results_are_capped_so_one_call_cannot_flood_the_context():
    huge = [
        {
            "document_id": "d", "filename": "big.md", "chunk_index": i,
            "score": 0.5, "content": "x" * 2_000,
        }
        for i in range(20)
    ]
    out = render_document_hits(huge)
    assert len(out) < 7_000 and out.endswith("[truncated]")
