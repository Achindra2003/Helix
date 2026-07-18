"""The built-in tool catalog (see the package docstring for the policy layers).

Every handler returns a *string* — the exact text folded back to the model as
the tool result. Results are honest about emptiness ("nothing found" is an
answer, not an error) and bounded in size so one tool call can't flood the
context window. Handlers never raise to the model: the agent graph catches
and reports failures as results, so a broken tool degrades the answer, not
the run.

Retrieval tools reuse the existing measured substrates — `DocumentIndex.search`
(hybrid dense+BM25, calibrated on the golden set) and
`EmbeddingIndex.search_workspace` (which applies the caller's visibility:
shared threads + their own private ones, never a teammate's private thread).
The agent inherits those guarantees instead of re-implementing retrieval.
"""
from __future__ import annotations

from ..config import settings
from . import ToolSpec

# Cap per tool result: enough for several full chunks, small enough that a
# handful of calls can't crowd the history out of the context window.
_RESULT_CHARS = 6_000

_QUERY_PARAM = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "What to search for."}
    },
    "required": ["query"],
}


def _clip(text: str) -> str:
    return text if len(text) <= _RESULT_CHARS else text[:_RESULT_CHARS] + "\n[truncated]"


def render_document_hits(hits: list[dict]) -> str:
    """Tool-result text for `DocumentIndex.search` hits."""
    if not hits:
        return "No relevant documents found in the workspace knowledge base."
    parts = [
        f"[{h['filename']} — part {h['chunk_index'] + 1}, relevance {h['score']}]\n"
        f"{h['content']}"
        for h in hits
    ]
    return _clip("\n\n".join(parts))


def render_conversation_hits(items: list[dict]) -> str:
    """Tool-result text for `EmbeddingIndex.search_workspace` items."""
    if not items:
        return "No relevant messages found in this workspace's conversations."
    parts = [
        f"[conversation \"{i['conversation_title']}\" — {i['role']}, "
        f"relevance {i['score']}]\n{i['excerpt']}"
        for i in items
    ]
    return _clip("\n\n".join(parts))


def render_web_results(data: dict) -> str:
    """Tool-result text for a Tavily search response."""
    parts = []
    if data.get("answer"):
        parts.append(f"Summary: {data['answer']}")
    for r in data.get("results", []) or []:
        title = r.get("title") or r.get("url") or "result"
        snippet = (r.get("content") or "").strip()
        parts.append(f"[{title}]({r.get('url', '')})\n{snippet}")
    if not parts:
        return "The web search returned no results."
    return _clip("\n\n".join(parts))


def make_tools(
    *,
    workspace_id: str,
    viewer_id: str,
    documents,
    embeddings,
    tavily_key: str = "",
) -> list[ToolSpec]:
    """The full catalog for one (workspace, viewer) pair.

    `viewer_id` matters: conversation search runs *as the caller*, so the
    agent can never surface a private thread its user couldn't open —
    the tool layer inherits RBAC instead of becoming a hole in it.
    """

    async def search_knowledge_base(query: str = "") -> str:
        hits = await documents.search(workspace_id, query, k=settings.grounding_k)
        return render_document_hits(hits)

    async def search_conversations(query: str = "") -> str:
        items = await embeddings.search_workspace(workspace_id, viewer_id, query, k=6)
        return render_conversation_hits(items)

    async def web_search(query: str = "") -> str:
        if not tavily_key:  # defensive: an unavailable tool is never bound
            return "Web search is not configured on this deployment."
        import httpx

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "max_results": 5,
                    "include_answer": True,
                },
            )
            resp.raise_for_status()
            return render_web_results(resp.json())

    return [
        ToolSpec(
            name="search_knowledge_base",
            description=(
                "Search the workspace's uploaded documents (specs, runbooks, "
                "notes). Use for questions about this team's own files."
            ),
            parameters=_QUERY_PARAM,
            handler=search_knowledge_base,
        ),
        ToolSpec(
            name="search_conversations",
            description=(
                "Search this workspace's past conversations for earlier "
                "discussions, decisions, or answers."
            ),
            parameters=_QUERY_PARAM,
            handler=search_conversations,
        ),
        ToolSpec(
            name="web_search",
            description=(
                "Search the live web for current, external information. "
                "Requires human approval for each call."
            ),
            parameters=_QUERY_PARAM,
            handler=web_search,
            sensitive=True,  # leaves the workspace ⇒ approval-gated
            available=bool(tavily_key),
        ),
    ]
