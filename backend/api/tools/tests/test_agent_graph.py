"""The real LangGraph agent graph, driven by a scripted fake LLM.

These tests prove the three structural properties `build_agent_graph`
promises — hermetically, because the graph is identical whether the LLM is
ChatGroq or a script:

1. Only bound tools exist in the model's world (the allowlist is a binding
   decision, not a runtime refusal).
2. A sensitive call cannot execute without an explicit human approval — the
   checkpoint interrupt *is* the gate; denial folds refusals back so the
   model must answer without the tool.
3. Tool results fold into state as ToolMessages and the loop terminates.
"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from api.tools import ToolSpec
from api.tools.agent import build_agent_graph


class ScriptedLLM:
    """Plays back canned AIMessages; records what tools were bound to it."""

    def __init__(self, script):
        self._script = list(script)
        self.bound_schemas = None
        self.seen = []  # message lists per call, for context assertions

    def bind_tools(self, schemas):
        self.bound_schemas = schemas
        return self

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        return self._script.pop(0)


def _call(name, query, call_id="c1"):
    return {"name": name, "args": {"query": query}, "id": call_id, "type": "tool_call"}


def _tool(name, handler, *, sensitive=False):
    return ToolSpec(
        name=name,
        description=f"{name} tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=handler,
        sensitive=sensitive,
    )


async def _noop(**kw):
    return "unused"


def _build(script, tools):
    llm = ScriptedLLM(script)
    graph, config, make_inputs = build_agent_graph(
        thread_id="t-test", tools=tools, llm=llm
    )
    return llm, graph, config, make_inputs


async def test_plain_answer_never_touches_tools():
    called = []

    async def spy(**kw):
        called.append(kw)
        return "result"

    llm, graph, config, make_inputs = _build(
        [AIMessage(content="Just an answer.")], [_tool("search_knowledge_base", spy)]
    )
    state = await graph.ainvoke(make_inputs([{"role": "user", "content": "hi"}]), config)
    assert state["messages"][-1].content == "Just an answer."
    assert called == []
    # The tool *was* offered (bound) — the model simply didn't need it.
    assert [s["function"]["name"] for s in llm.bound_schemas] == ["search_knowledge_base"]


async def test_safe_tool_round_trip_folds_the_result_back():
    async def kb(query=""):
        return f"KB says: rollback via router swap (asked: {query})"

    llm, graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("search_knowledge_base", "rollback")]),
            AIMessage(content="Per the runbook, swap the router back."),
        ],
        [_tool("search_knowledge_base", kb)],
    )
    state = await graph.ainvoke(
        make_inputs([{"role": "user", "content": "how do we roll back?"}]), config
    )
    # No interrupt for safe tools: the run completed in one invoke.
    assert state["messages"][-1].content == "Per the runbook, swap the router back."
    tool_msgs = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1 and "router swap" in tool_msgs[0].content
    # The model's second call saw the tool result in its context.
    assert any(isinstance(m, ToolMessage) for m in llm.seen[1])


async def test_sensitive_call_pauses_and_approval_executes_it():
    called = []

    async def web(query=""):
        called.append(query)
        return "the web says 42"

    llm, graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("web_search", "meaning of life")]),
            AIMessage(content="It's 42."),
        ],
        [_tool("web_search", web, sensitive=True)],
    )
    await graph.ainvoke(make_inputs([{"role": "user", "content": "q"}]), config)
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("gate",)  # paused BEFORE the gate — nothing ran
    assert called == []

    await graph.aupdate_state(config, {"decision": "approve"})
    state = await graph.ainvoke(None, config)
    assert called == ["meaning of life"]
    assert state["messages"][-1].content == "It's 42."
    assert (await graph.aget_state(config)).next == ()


async def test_denial_never_executes_and_the_model_answers_without_it():
    called = []

    async def web(query=""):
        called.append(query)
        return "never seen"

    llm, graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("web_search", "secret")]),
            AIMessage(content="I couldn't check the web for that."),
        ],
        [_tool("web_search", web, sensitive=True)],
    )
    await graph.ainvoke(make_inputs([{"role": "user", "content": "q"}]), config)
    await graph.aupdate_state(config, {"decision": "deny"})
    state = await graph.ainvoke(None, config)

    assert called == []  # the handler never ran
    denials = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(denials) == 1 and "declined" in denials[0].content
    assert state["messages"][-1].content == "I couldn't check the web for that."
    # The model saw the denial when it answered.
    assert any("declined" in getattr(m, "content", "") for m in llm.seen[-1])


async def test_hallucinated_tool_name_comes_back_as_an_error_result():
    llm, graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("delete_everything", "now")]),
            AIMessage(content="That tool doesn't exist; here's what I know."),
        ],
        [_tool("search_knowledge_base", _noop)],
    )
    state = await graph.ainvoke(make_inputs([{"role": "user", "content": "q"}]), config)
    tool_msgs = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].status == "error" and "does not exist" in tool_msgs[0].content


async def test_broken_tool_degrades_the_answer_not_the_run():
    async def broken(**kw):
        raise RuntimeError("index unavailable")

    llm, graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("search_knowledge_base", "x")]),
            AIMessage(content="The search failed, but generally..."),
        ],
        [_tool("search_knowledge_base", broken)],
    )
    state = await graph.ainvoke(make_inputs([{"role": "user", "content": "q"}]), config)
    tool_msgs = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs[0].status == "error" and "index unavailable" in tool_msgs[0].content
    assert state["messages"][-1].content.startswith("The search failed")


async def test_no_tools_means_the_model_is_never_offered_any():
    llm = ScriptedLLM([AIMessage(content="plain")])
    graph, config, make_inputs = build_agent_graph(
        thread_id="t-none", tools=[], llm=llm
    )
    state = await graph.ainvoke(make_inputs([{"role": "user", "content": "q"}]), config)
    assert state["messages"][-1].content == "plain"
    assert llm.bound_schemas is None  # bind_tools never called


async def test_system_frame_reaches_the_model_as_a_system_message():
    llm, graph, config, make_inputs = _build([AIMessage(content="ok")], [])
    inputs = make_inputs(
        [
            {"role": "system", "content": "You are Helix."},
            {"role": "assistant", "content": "earlier reply"},
            {"role": "user", "content": "q"},
        ]
    )
    await graph.ainvoke(inputs, config)
    first = llm.seen[0][0]
    assert first.content == "You are Helix." and first.type == "system"
    assert [m.type for m in llm.seen[0]] == ["system", "ai", "human"]


async def test_runaway_tool_loop_hits_the_recursion_limit():
    """A model that never stops asking for tools terminates with an error
    instead of looping forever — max_tool_rounds bounds the run."""
    async def kb(**kw):
        return "more"

    forever = [
        AIMessage(content="", tool_calls=[_call("search_knowledge_base", "again", f"c{i}")])
        for i in range(50)
    ]
    llm = ScriptedLLM(forever)
    graph, config, make_inputs = build_agent_graph(
        thread_id="t-loop", tools=[_tool("search_knowledge_base", kb)],
        llm=llm, max_tool_rounds=2,
    )
    import pytest
    from langgraph.errors import GraphRecursionError

    with pytest.raises(GraphRecursionError):
        await graph.ainvoke(make_inputs([{"role": "user", "content": "q"}]), config)
