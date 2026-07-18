"""The agent tool loop — the third producer, and the piece that makes FR-14
real: model requests a tool → allowlist already decided what it can see →
sensitive calls pause for human approval → results fold back → the model
answers grounded in what it found.

Same two-layer split as deep_reasoning.py, for the same reason:

- `AgentProducer` — pure event-mapping over anything exposing
  ``astream``/``aget_state``/``aupdate_state``. No LangGraph import, so the
  mapping is fast and deterministic to test against a fake graph.
- `build_agent_graph()` — the real LangGraph wiring: an ``agent`` node
  (LLM with bound tools), a ``tools`` node (execute + fold back), and a
  ``gate`` node the graph *interrupts before* whenever a requested call is
  sensitive — the human-in-the-loop pause is a checkpoint, not a busy-wait.

The run rides the existing deep-run machinery (`RunManager` +
`engine.ResumableRun`): the approval pause is a `Waiting` event exactly like
a steer pause, and `resume("approve"|"deny")` is a steer with a decision.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Callable

from ..conversation.context import build_messages
from ..conversation.events import (
    Complete,
    Event,
    Grounding,
    Token,
    ToolCall,
    ToolResult,
    Waiting,
)
from ..conversation.producer import Grounder, Recaller
from . import ToolSpec, openai_schema

# Tool-result previews on the event stream stay short; the model sees the
# full result inside the graph state.
_PREVIEW_CHARS = 400


def _calls_of(message: Any) -> list[dict]:
    """LangChain tool_calls, tolerantly: [{'name','args','id',...}, ...]."""
    return list(getattr(message, "tool_calls", None) or [])


class AgentProducer:
    """Maps an agent-graph ``astream`` onto the run event contract.

    Context building matches chat exactly (references, semantic recall, file
    grounding) — the agent is everyday chat *plus hands*, not a separate
    universe. `specs` gives the producer each tool's sensitivity so the
    `tool_call` frames can warn the UI an approval pause is coming.
    """

    def __init__(
        self,
        *,
        graph: Any,
        graph_config: dict[str, Any],
        make_inputs: Callable[[list[dict]], dict[str, Any]],
        specs: dict[str, ToolSpec] | None = None,
        references: list | None = None,
        recaller: Recaller | None = None,
        grounder: Grounder | None = None,
        should_stop: Callable[[], bool] | None = None,
        deadline_s: float | None = None,
    ) -> None:
        self._graph = graph
        self._graph_config = graph_config
        self._make_inputs = make_inputs
        self._specs = specs or {}
        self._references = references
        self._recaller = recaller
        self._grounder = grounder
        self._should_stop = should_stop
        self._deadline_s = deadline_s
        self._streamed = False  # any messages-mode token reached the client
        self._final = ""  # last no-tool-call AI content (non-streaming fallback)

    async def run(self, history: list) -> AsyncIterator[Event]:
        recalled = await self._recaller(history) if self._recaller else None
        grounding_block = ""
        if self._grounder is not None:
            grounding_block, citations = await self._grounder(history)
            if citations:
                yield Grounding(items=citations)
        messages = build_messages(
            history,
            references=self._references,
            recalled=recalled,
            grounding=grounding_block or None,
        )
        async for event in self._drive(self._make_inputs(messages)):
            yield event

    async def resume(self, decision: str) -> AsyncIterator[Event]:
        """Resume an approval-paused run. `decision` is "approve" or "deny";
        anything else counts as deny — the safe reading of an unclear answer."""
        update = getattr(self._graph, "aupdate_state", None)
        if update is not None:
            verdict = "approve" if decision.strip().lower() == "approve" else "deny"
            await update(self._graph_config, {"decision": verdict})
        async for event in self._drive(None):  # None -> continue the checkpoint
            yield event

    def _map_update(self, node_name: str, delta: dict) -> list[Event]:
        """Events for one node's state delta."""
        out: list[Event] = []
        msgs = delta.get("messages") or []
        if not isinstance(msgs, list):
            msgs = [msgs]
        if node_name == "agent":
            for m in msgs:
                calls = _calls_of(m)
                for c in calls:
                    spec = self._specs.get(c.get("name", ""))
                    out.append(
                        ToolCall(
                            id=str(c.get("id") or ""),
                            name=str(c.get("name") or ""),
                            arguments=dict(c.get("args") or {}),
                            sensitive=bool(spec.sensitive) if spec else False,
                        )
                    )
                content = getattr(m, "content", "")
                if isinstance(content, str) and content and not calls:
                    self._final = content
        elif node_name in ("tools", "gate"):
            # Both emit ToolMessages: real results from `tools`, denial notes
            # from `gate`. status rides on the message itself.
            for m in msgs:
                call_id = getattr(m, "tool_call_id", "") or ""
                status = getattr(m, "status", "success")
                content = getattr(m, "content", "")
                out.append(
                    ToolResult(
                        id=str(call_id),
                        name=str(getattr(m, "name", "") or ""),
                        content=str(content)[:_PREVIEW_CHARS],
                        status="denied" if node_name == "gate"
                        else ("error" if status == "error" else "ok"),
                    )
                )
        return out

    async def _drive(self, inputs) -> AsyncIterator[Event]:
        deadline = time.monotonic() + self._deadline_s if self._deadline_s else None
        try:
            async for mode, data in self._graph.astream(
                inputs, config=self._graph_config, stream_mode=["updates", "messages"]
            ):
                if deadline is not None and time.monotonic() > deadline:
                    yield Complete(stop_reason="deadline", status="done")
                    return
                if self._should_stop is not None and self._should_stop():
                    yield Complete(stop_reason="stopped", status="killed")
                    return

                if mode == "messages":
                    chunk, meta = data
                    # Stream only the agent node's prose. Tool-call chunks
                    # carry empty content, so this is exactly the visible reply.
                    if (meta or {}).get("langgraph_node") == "agent":
                        text = getattr(chunk, "content", "") or ""
                        if isinstance(text, str) and text:
                            self._streamed = True
                            yield Token(text=text)
                    continue

                # mode == "updates": {node_name: state_delta}
                node_name = next(iter(data))
                if node_name.startswith("__"):  # control markers, not steps
                    continue
                for event in self._map_update(node_name, data[node_name] or {}):
                    yield event

            snapshot = await self._graph.aget_state(self._graph_config)
            pending = tuple(getattr(snapshot, "next", ()) or ())
            if "gate" in pending:
                yield Waiting(reason="approval")
                return

            if not self._streamed and self._final:
                yield Token(text=self._final)
            yield Complete(stop_reason="answered", status="done")
        except Exception as exc:  # surface graph failures as a terminal event
            yield Complete(stop_reason=f"error: {exc}", status="error")


def build_agent_graph(
    *,
    thread_id: str,
    tools: list[ToolSpec],
    groq_api_key: str = "",
    groq_model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.3,
    max_tool_rounds: int = 5,
    llm: Any = None,
    extra_callbacks: list | None = None,
):
    """Construct the real agent graph. Returns ``(graph, graph_config,
    make_inputs)``.

    The graph (the LangGraph shape interviews ask you to whiteboard):

        START → agent ─(no tool calls)────────────→ END
                  │(sensitive call)   │(safe calls)
                  ▼                   ▼
        [interrupt] gate ─(approved)→ tools ──→ agent
                  └─(denied: denial ToolMessages)→ agent

    Three properties enforced *structurally*, not by prompt:
    - Only `tools` (bound at build from the allowlist) exist in the model's
      world — an un-allowed tool cannot be called because it was never offered.
    - A sensitive call cannot execute without a human decision: the graph
      checkpoint-pauses before `gate`, and only an explicit approval routes
      to the `tools` node.
    - The loop terminates: the recursion limit derived from
      `max_tool_rounds` stops a model that never stops asking.

    `llm=None` builds a ChatGroq from the given key (the production path);
    tests inject a scripted fake and exercise the identical graph.
    """
    # Lazy imports: LangGraph/LangChain load only when an agent run starts.
    from typing import Annotated, TypedDict

    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages

    if llm is None:
        from langchain_groq import ChatGroq

        llm = ChatGroq(
            model=groq_model, temperature=temperature, api_key=groq_api_key or None
        )

    specs = {t.name: t for t in tools}
    model = llm.bind_tools([openai_schema(t) for t in tools]) if tools else llm

    # Functional TypedDict form: the module uses postponed annotations, so a
    # class body here would leave string annotations LangGraph can't resolve
    # against these function-local imports. add_messages is the reducer: nodes
    # return *appends*, never replacements — the whole tool transcript
    # (AI request → ToolMessage results) stays in state, which is what lets
    # the model read its own tool results.
    AgentState = TypedDict(
        "AgentState",
        {
            "messages": Annotated[list, add_messages],
            # human verdict injected while paused at the gate
            "decision": str,
        },
    )

    async def agent(state: dict) -> dict:
        reply = await model.ainvoke(state["messages"])
        return {"messages": [reply]}

    def route_agent(state: dict) -> str:
        calls = _calls_of(state["messages"][-1])
        if not calls:
            return END
        if any(specs[c["name"]].sensitive for c in calls if c["name"] in specs):
            return "gate"  # compiled with interrupt_before: the run pauses here
        return "tools"

    def gate(state: dict) -> dict:
        """Runs only after a human resumed the checkpoint with a decision.

        Approval passes the pending calls through untouched (routing then
        sends them to `tools`); denial answers each call with a denial
        ToolMessage, so the model must respond without the tool — and can say
        what it couldn't check.
        """
        if state.get("decision") == "approve":
            return {"decision": ""}
        denials = [
            ToolMessage(
                content=(
                    "The user declined this tool call. Answer from what you "
                    "already have, and say what you could not check."
                ),
                tool_call_id=c["id"],
                name=c.get("name", ""),
                status="error",
            )
            for c in _calls_of(state["messages"][-1])
        ]
        return {"decision": "", "messages": denials}

    def route_gate(state: dict) -> str:
        # Approval left the tool-call request as the last message; denial
        # appended ToolMessages. Routing reads the state, not a flag.
        return "tools" if _calls_of(state["messages"][-1]) else "agent"

    async def run_tools(state: dict) -> dict:
        request = next(m for m in reversed(state["messages"]) if _calls_of(m))
        results = []
        for call in _calls_of(request):
            spec = specs.get(call["name"])
            status = "success"
            if spec is None:  # model hallucinated a tool name
                content = f"Tool '{call['name']}' does not exist."
                status = "error"
            else:
                try:
                    content = await spec.handler(**(call.get("args") or {}))
                except Exception as exc:  # a broken tool is a result, not a crash
                    content = f"Tool error ({type(exc).__name__}): {exc}"
                    status = "error"
            results.append(
                ToolMessage(
                    content=str(content),
                    tool_call_id=call["id"],
                    name=call["name"],
                    status=status,
                )
            )
        return {"messages": results}

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("gate", gate)
    g.add_node("tools", run_tools)
    g.add_edge(START, "agent")
    g.add_conditional_edges(
        "agent", route_agent, {"gate": "gate", "tools": "tools", END: END}
    )
    g.add_conditional_edges("gate", route_gate, {"tools": "tools", "agent": "agent"})
    g.add_edge("tools", "agent")
    # MemorySaver: in-process checkpoints, same lifetime as the RunManager
    # handles that own these runs. The restart-surviving SQL checkpointer is
    # the documented seam (checkpointer= here).
    graph = g.compile(checkpointer=MemorySaver(), interrupt_before=["gate"])

    graph_config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": list(extra_callbacks or []),
        # Per round the graph takes ≤3 supersteps (agent → [gate] → tools),
        # plus the closing agent turn and slack for denial re-routes.
        "recursion_limit": 3 * max(1, max_tool_rounds) + 4,
    }

    def make_inputs(messages: list[dict]) -> dict:
        by_role = {"system": SystemMessage, "assistant": AIMessage}
        return {
            "messages": [
                by_role.get(m["role"], HumanMessage)(content=m["content"])
                for m in messages
            ],
            "decision": "",
        }

    return graph, graph_config, make_inputs
