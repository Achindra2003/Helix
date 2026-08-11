"""The agent layer's instruments.

Before these, `run_tools` executed a handler, caught whatever came back, and
returned a string — the only record a call ever happened was a 400-character
preview on a stream nobody kept, and the approval gate (the product's whole
safety claim) left no trace at all. These prove the two instruments the LLM
layer already had now exist here too, and that neither one can break a run.
"""
import pytest
from langchain_core.messages import AIMessage
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from api.tools import ToolSpec
from api.tools.agent import build_agent_graph
from api.tools.telemetry import (
    STATUS_DENIED,
    STATUS_ERROR,
    STATUS_OK,
    ToolObserver,
    digest,
)


class ScriptedLLM:
    def __init__(self, script):
        self._script = list(script)

    def bind_tools(self, schemas):
        return self

    async def ainvoke(self, messages):
        return self._script.pop(0)


def _call(name, query="q", call_id="c1"):
    return {"name": name, "args": {"query": query}, "id": call_id, "type": "tool_call"}


async def _ok(**kw):
    """A handler that succeeds. Must be async — `run_tools` awaits it, and a
    sync lambda would fail on the await rather than in the tool."""
    return "fine"


def _tool(name, handler, *, sensitive=False):
    return ToolSpec(
        name=name,
        description=f"{name} tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=handler,
        sensitive=sensitive,
    )


@pytest.fixture
def spans():
    """An in-memory exporter, installed for one test.

    The process tracer is resolved late (`telemetry.tracer()`), which is what
    lets a test install its own provider and see the spans production would
    export — without any of it leaving the process.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # Save the raw module global, not `get_tracer_provider()`. That call
    # returns a *proxy* which resolves through this same global — restoring it
    # would point the global at something that reads the global, and the next
    # `tracer()` recurses until the stack ends.
    previous = trace._TRACER_PROVIDER  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER = provider  # type: ignore[attr-defined]
    yield exporter
    trace._TRACER_PROVIDER = previous  # type: ignore[attr-defined]


@pytest.fixture
def ledger(monkeypatch):
    """Capture ledger writes without a database.

    `record_tool_call` is fire-and-forget by design — it schedules a task and
    returns — so asserting on rows would mean racing an event loop for a
    property that is about *what* is recorded, not *where*.
    """
    rows = []
    monkeypatch.setattr(
        "api.tools.agent.NULL_OBSERVER", ToolObserver(), raising=False
    )
    import api.tools.telemetry as tel

    monkeypatch.setattr(tel, "record_tool_call", lambda **kw: rows.append(kw))
    return rows


async def _run(graph, config, make_inputs, prompt="go"):
    inputs = make_inputs([{"role": "user", "content": prompt}])
    async for _ in graph.astream(inputs, config=config, stream_mode=["updates"]):
        pass


def _build(script, tools, observer):
    graph, config, make_inputs = build_agent_graph(
        thread_id=f"t-{id(script)}",
        tools=tools,
        llm=ScriptedLLM(script),
        observer=observer,
    )
    return graph, config, make_inputs


async def test_a_successful_call_is_spanned_and_ledgered(spans, ledger):
    async def ok(**kw):
        return "sixteen characters"

    obs = ToolObserver(workspace_id="w1", run_id="r1")
    graph, config, make_inputs = _build(
        [AIMessage(content="", tool_calls=[_call("search")]), AIMessage(content="done")],
        [_tool("search", ok)],
        obs,
    )
    await _run(graph, config, make_inputs)

    names = [s.name for s in spans.get_finished_spans()]
    assert "execute_tool search" in names
    span = next(s for s in spans.get_finished_spans() if s.name == "execute_tool search")
    assert span.attributes["gen_ai.operation.name"] == "execute_tool"
    assert span.attributes["gen_ai.tool.name"] == "search"
    # The run id is what groups a tool call under the run that requested it.
    assert span.attributes["helix.run_id"] == "r1"
    assert span.attributes["helix.workspace_id"] == "w1"

    assert len(ledger) == 1
    row = ledger[0]
    assert row["tool_name"] == "search"
    assert row["status"] == STATUS_OK
    assert row["result_chars"] == len("sixteen characters")
    assert row["decided_by"] is None, "an automatic call had no human in it"


async def test_a_failing_tool_is_recorded_as_an_error_not_a_crash(spans, ledger):
    async def boom(**kw):
        raise RuntimeError("upstream is down")

    obs = ToolObserver(workspace_id="w1", run_id="r1")
    graph, config, make_inputs = _build(
        [AIMessage(content="", tool_calls=[_call("search")]), AIMessage(content="sorry")],
        [_tool("search", boom)],
        obs,
    )
    await _run(graph, config, make_inputs)  # must not raise

    assert ledger[0]["status"] == STATUS_ERROR
    assert "RuntimeError" in ledger[0]["error"]


async def test_a_hallucinated_tool_name_is_recorded(ledger):
    """A model repeatedly reaching for a tool it cannot have is a real signal —
    usually a stale allowlist — and it is invisible if only executions log."""
    obs = ToolObserver(workspace_id="w1", run_id="r1")
    graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("no_such_tool")]),
            AIMessage(content="ok"),
        ],
        [_tool("search", _ok)],
        obs,
    )
    await _run(graph, config, make_inputs)

    assert ledger[0]["tool_name"] == "no_such_tool"
    assert ledger[0]["status"] == STATUS_ERROR


async def test_an_approval_names_who_gave_it(spans, ledger):
    """The gate is the product's safety story and it used to leave no trace.
    "Who let the agent call the web?" must be answerable a month later."""
    async def ok(**kw):
        return "the web says hello"

    obs = ToolObserver(workspace_id="w1", run_id="r1")
    graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("web_search")]),
            AIMessage(content="done"),
        ],
        [_tool("web_search", ok, sensitive=True)],
        obs,
    )
    await _run(graph, config, make_inputs)  # pauses before the gate

    # A human approves, naming themselves.
    await graph.aupdate_state(config, {"decision": "approve", "decided_by": "u-42"})
    async for _ in graph.astream(None, config=config, stream_mode=["updates"]):
        pass

    assert any(s.name == "approval web_search" for s in spans.get_finished_spans())
    executed = [r for r in ledger if r["status"] == STATUS_OK]
    assert executed and executed[0]["decided_by"] == "u-42"


async def test_a_denial_is_recorded_and_is_not_an_error(spans, ledger):
    """A human refusing a tool is the gate working. Counting it as a failure
    would make the safety feature look like a fault in every dashboard."""
    obs = ToolObserver(workspace_id="w1", run_id="r1")
    graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("web_search")]),
            AIMessage(content="I could not check that"),
        ],
        [_tool("web_search", _ok, sensitive=True)],
        obs,
    )
    await _run(graph, config, make_inputs)

    await graph.aupdate_state(config, {"decision": "deny", "decided_by": "u-42"})
    async for _ in graph.astream(None, config=config, stream_mode=["updates"]):
        pass

    denied = [r for r in ledger if r["status"] == STATUS_DENIED]
    assert denied, "a denial must leave a record — it is the interesting event"
    assert denied[0]["decided_by"] == "u-42"
    assert not [r for r in ledger if r["status"] == STATUS_ERROR]


async def test_arguments_are_digested_not_stored(ledger):
    """A search query is a sentence someone typed. The ledger is an operational
    record, not a second copy of the conversation."""
    obs = ToolObserver(workspace_id="w1", run_id="r1")
    secret = "our unreleased pricing model"
    graph, config, make_inputs = _build(
        [
            AIMessage(content="", tool_calls=[_call("search", secret)]),
            AIMessage(content="done"),
        ],
        [_tool("search", _ok)],
        obs,
    )
    await _run(graph, config, make_inputs)

    assert secret not in repr(ledger)
    assert ledger[0]["args_digest"] == digest({"query": secret})


def test_identical_calls_share_a_digest():
    """So a model stuck retrying the same search is visible in the ledger."""
    assert digest({"query": "a", "k": 1}) == digest({"k": 1, "query": "a"})
    assert digest({"query": "a"}) != digest({"query": "b"})


async def test_telemetry_costs_nothing_when_unconfigured(ledger):
    """The default path: no OTLP endpoint, so no SDK provider is installed and
    `tracer()` hands back the API's no-op. The run must be unaffected."""
    obs = ToolObserver(workspace_id="w1", run_id="r1")
    graph, config, make_inputs = _build(
        [AIMessage(content="", tool_calls=[_call("search")]), AIMessage(content="done")],
        [_tool("search", _ok)],
        obs,
    )
    await _run(graph, config, make_inputs)  # no provider installed by this test
    assert ledger[0]["status"] == STATUS_OK
