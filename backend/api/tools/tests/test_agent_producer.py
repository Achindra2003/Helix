"""AgentProducer event-mapping against a fake agent-shaped graph.

Mirrors test_deep_reasoning.py: the producer is pure mapping, so a fake graph
yielding the same `(mode, data)` tuples proves the contract — ToolCall /
ToolResult frames for the loop, Token for the reply, Waiting(reason="approval")
on a gate interrupt, Complete at the end — and that `engine.ResumableRun`
persists the assistant node only when the run truly finishes.
"""
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from api.conversation.engine import ResumableRun
from api.conversation.events import (
    AssistantNode,
    Complete,
    Token,
    ToolCall,
    ToolResult,
    Waiting,
)
from api.conversation.store import InMemoryStore
from api.tools import ToolSpec
from api.tools.agent import AgentProducer


class _Chunk:
    def __init__(self, content):
        self.content = content


class FakeGraph:
    """Canned astream tuples per drive; `next_` drives the interrupt check."""

    def __init__(self, segments, next_by_segment=None):
        self._segments = list(segments)
        self._next = list(next_by_segment or [()] * len(segments))
        self.updates = []  # aupdate_state payloads (the approval decisions)
        self._segment = -1

    async def astream(self, inputs, config, stream_mode):
        self._segment += 1
        for ev in self._segments[self._segment]:
            yield ev

    async def aget_state(self, config):
        return SimpleNamespace(next=self._next[self._segment])

    async def aupdate_state(self, config, values):
        self.updates.append(values)


def _specs():
    async def noop(**kw):
        return "x"

    return {
        "web_search": ToolSpec(
            name="web_search", description="d", parameters={}, handler=noop,
            sensitive=True,
        ),
        "search_knowledge_base": ToolSpec(
            name="search_knowledge_base", description="d", parameters={}, handler=noop,
        ),
    }


def _producer(graph, **kw):
    return AgentProducer(
        graph=graph, graph_config={}, make_inputs=lambda msgs: {"messages": msgs},
        specs=_specs(), **kw,
    )


async def _history():
    store = InMemoryStore()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    node = await store.add_node(
        branch_id=conv.default_branch_id, role="user", content="q", author_id="u1"
    )
    return store, conv.default_branch_id, [node]


_TOOL_ROUND = [
    (
        "updates",
        {"agent": {"messages": [AIMessage(content="", tool_calls=[
            {"name": "search_knowledge_base", "args": {"query": "rollback"}, "id": "c1", "type": "tool_call"}
        ])]}},
    ),
    (
        "updates",
        {"tools": {"messages": [ToolMessage(content="KB result " * 200, tool_call_id="c1", name="search_knowledge_base")]}},
    ),
    ("messages", (_Chunk("Per the "), {"langgraph_node": "agent"})),
    ("messages", (_Chunk("runbook."), {"langgraph_node": "agent"})),
    ("updates", {"agent": {"messages": [AIMessage(content="Per the runbook.")]}}),
]


async def test_maps_tool_loop_tokens_and_completes():
    _, _, history = await _history()
    events = [e async for e in _producer(FakeGraph([_TOOL_ROUND])).run(history)]

    calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(calls) == 1
    assert calls[0].name == "search_knowledge_base"
    assert calls[0].arguments == {"query": "rollback"}
    assert calls[0].sensitive is False

    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(results) == 1 and results[0].status == "ok"
    assert len(results[0].content) <= 400  # preview, not the full payload

    assert [t.text for t in events if isinstance(t, Token)] == ["Per the ", "runbook."]
    assert isinstance(events[-1], Complete) and events[-1].status == "done"


async def test_sensitive_call_yields_waiting_for_approval():
    _, _, history = await _history()
    pause_segment = [
        (
            "updates",
            {"agent": {"messages": [AIMessage(content="", tool_calls=[
                {"name": "web_search", "args": {"query": "x"}, "id": "c9", "type": "tool_call"}
            ])]}},
        ),
        ("updates", {"__interrupt__": ()}),  # control marker: skipped, not mapped
    ]
    events = [
        e async for e in _producer(FakeGraph([pause_segment], [("gate",)])).run(history)
    ]
    call = next(e for e in events if isinstance(e, ToolCall))
    assert call.sensitive is True  # the UI can warn: approval incoming
    assert isinstance(events[-1], Waiting) and events[-1].reason == "approval"
    assert not any(isinstance(e, Complete) for e in events)


async def test_resume_normalizes_the_decision_and_denial_maps_as_denied():
    _, _, history = await _history()
    deny_segment = [
        (
            "updates",
            {"gate": {"messages": [ToolMessage(
                content="The user declined this tool call.", tool_call_id="c9",
                name="web_search", status="error",
            )]}},
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="Couldn't check.")]}}),
    ]
    graph = FakeGraph([deny_segment])
    producer = _producer(graph)
    events = [e async for e in producer.resume("whatever")]  # unclear ⇒ deny

    assert graph.updates == [{"decision": "deny"}]
    result = next(e for e in events if isinstance(e, ToolResult))
    assert result.status == "denied" and result.name == "web_search"
    # No messages-mode streaming in this fake: the final content falls back
    # to a single Token so the persisted reply is never empty.
    assert [t.text for t in events if isinstance(t, Token)] == ["Couldn't check."]
    assert isinstance(events[-1], Complete)


async def test_resume_approve_passes_through():
    graph = FakeGraph([[("updates", {"agent": {"messages": [AIMessage(content="ok")]}})]])
    events = [e async for e in _producer(graph).resume("  APPROVE ")]
    assert graph.updates == [{"decision": "approve"}]
    assert isinstance(events[-1], Complete)


async def test_graph_failure_is_a_terminal_event_not_an_exception():
    class ExplodingGraph:
        async def astream(self, inputs, config, stream_mode):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        async def aget_state(self, config):
            return SimpleNamespace(next=())

    _, _, history = await _history()
    events = [e async for e in _producer(ExplodingGraph()).run(history)]
    assert isinstance(events[-1], Complete) and events[-1].status == "error"
    assert "boom" in events[-1].stop_reason


async def test_resumable_run_persists_only_after_approval_completes():
    """Through the same ResumableRun deep runs use: an approval pause leaves
    no assistant node; the resumed segment persists the full reply."""
    store, branch_id, _ = await _history()
    pause = [
        ("updates", {"agent": {"messages": [AIMessage(content="", tool_calls=[
            {"name": "web_search", "args": {"query": "x"}, "id": "c1", "type": "tool_call"}
        ])]}}),
    ]
    finish = [
        ("updates", {"tools": {"messages": [ToolMessage(content="found", tool_call_id="c1", name="web_search")]}}),
        ("updates", {"agent": {"messages": [AIMessage(content="It's 42.")]}}),
    ]
    producer = _producer(FakeGraph([pause, finish], [("gate",), ()]))
    run = ResumableRun(store=store, producer=producer, branch_id=branch_id)

    first = [e async for e in run.start(prompt="q2", author_id="u1")]
    assert isinstance(first[-1], Waiting) and run.paused
    assert not any(isinstance(e, AssistantNode) for e in first)

    second = [e async for e in run.steer("approve")]
    node = next(e for e in second if isinstance(e, AssistantNode))
    assert node.node.content == "It's 42."
