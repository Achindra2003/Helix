"""Deep Reasoning — the second producer (Ouroboros), mapping its LangGraph
`astream` events onto the one event contract.

Architecture: "one mount, two producers". `ChatProducer` and this both satisfy
the `Producer` Protocol, so `engine.send` runs either unchanged. Where chat emits
`Token`s, deep reasoning emits the richer trace the monitor renders —
`Step` (each reasoning transition), `Budget` (the token meter), `Waiting` (paused
for steer), `Complete` (why it halted) — plus `Token`s for the *final answer only*
(the `surface` node), so the persisted assistant message is the actionable answer,
not the whole stream of thoughts.

Two layers, deliberately split:
- `DeepReasoningProducer` — pure event-mapping over any object exposing
  `astream(...)` + `aget_state(...)`. No Ouroboros import, so it is fast and
  deterministic to test against a fake graph.
- `build_ouroboros_graph()` — the real wiring. Lazily imports the vendored
  engine and constructs the LLM *explicitly* from Helix-side config so Ouroboros
  never reads Helix's ambient `.env` (integration gotcha a) and the two provider
  enums never cross (gotcha b).
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Callable

from .context import render_seed
from .events import Budget, Complete, Event, Step, Token, Waiting

# Fields worth surfacing to the monitor from a node's state delta / running state.
_STEP_KEYS = (
    "thought",
    "synthesis",
    "surfaced_insight",
    "emotional_reading",
    "logical_reading",
    "memory_reading",
    "insights",
    "stability",
    "confidence",
    "stop_reason",
    "loop_guard",
    "tick",
)


def _default_make_inputs(seed: str) -> dict[str, Any]:
    """Minimal seed state. The real factory overrides this with the engine's
    full initial `OuroborosState`."""
    return {"seed": seed, "thought": seed}


class DeepReasoningProducer:
    """Maps an Ouroboros-shaped `astream` onto the run event contract.

    `graph` need only provide:
      - ``astream(inputs, config, stream_mode=["updates","messages"])`` yielding
        ``(mode, data)`` tuples (LangGraph's multi-mode streaming), and
      - ``aget_state(config)`` returning an object whose ``.next`` reveals a
        pending ``steer`` interrupt.
    """

    def __init__(
        self,
        *,
        graph: Any,
        graph_config: dict[str, Any],
        token_budget: int = 200_000,
        usage_reader: Callable[[], int] | None = None,
        make_inputs: Callable[[str], dict[str, Any]] = _default_make_inputs,
        seed_builder: Callable[[list], str] = render_seed,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        self._graph = graph
        self._graph_config = graph_config
        self._token_budget = token_budget
        self._usage_reader = usage_reader
        self._make_inputs = make_inputs
        self._seed_builder = seed_builder
        self._should_stop = should_stop
        self._state: dict[str, Any] = {}
        self._idx = 0
        self._answered = False

    def _merge(self, delta: dict[str, Any]) -> None:
        for key, val in (delta or {}).items():
            if key != "messages":
                self._state[key] = val

    def _payload(self) -> dict[str, Any]:
        return {k: self._state[k] for k in _STEP_KEYS if k in self._state}

    def _budget_event(self) -> Budget | None:
        if self._usage_reader is None:
            return None
        used = int(self._usage_reader())
        pct = round(used / self._token_budget, 4) if self._token_budget else 0.0
        return Budget(tokens_used=used, tokens_budget=self._token_budget, pct=pct)

    async def run(self, history: list) -> AsyncIterator[Event]:
        # Seed over the whole thread (recent context + the question), not just the
        # last line, so the engine reasons with the shared, branchable context.
        seed = self._seed_builder(history)
        self._idx = 0
        self._answered = False
        async for event in self._drive(self._make_inputs(seed)):
            yield event

    async def resume(self, human_input: str) -> AsyncIterator[Event]:
        """Resume a steer-paused run: inject `human_input`, continue from the
        checkpoint on the same `thread_id`, and keep mapping events.

        Pairs with the `Waiting(reason="steer")` `run` emits when the graph pauses
        at the `steer` interrupt. The step counter and answered flag carry over so
        the resumed trace continues seamlessly.
        """
        update = getattr(self._graph, "aupdate_state", None)
        if update is not None:
            await update(self._graph_config, {"human_input": human_input})
        async for event in self._drive(None):  # inputs=None -> continue checkpoint
            yield event

    async def _drive(self, inputs) -> AsyncIterator[Event]:
        """Map one `astream` pass (fresh run or checkpoint resume) onto events."""
        try:
            async for mode, data in self._graph.astream(
                inputs, config=self._graph_config, stream_mode=["updates", "messages"]
            ):
                # Cooperative kill: stop the run between events (RBAC-gated at the
                # endpoint). Persists whatever answer surfaced so far.
                if self._should_stop is not None and self._should_stop():
                    if not self._answered:
                        partial = self._state.get("synthesis") or self._state.get("thought") or ""
                        if partial:
                            yield Token(text=partial)
                    yield Complete(stop_reason="stopped", status="killed")
                    return

                if mode == "messages":
                    chunk, meta = data
                    # Stream only the final-answer node so the persisted assistant
                    # message is the crystallized answer, not every thought.
                    if (meta or {}).get("langgraph_node") == "surface":
                        text = getattr(chunk, "content", "") or ""
                        if text:
                            self._answered = True
                            yield Token(text=text)
                    continue

                # mode == "updates": {node_name: state_delta}
                node_name = next(iter(data))
                # Skip LangGraph internal markers (e.g. "__interrupt__") — they are
                # control signals, not reasoning steps, and would clutter the trace.
                if node_name.startswith("__"):
                    continue
                delta = data[node_name] or {}
                self._merge(delta)
                self._idx += 1
                yield Step(
                    idx=self._idx,
                    node=node_name,
                    depth=int(self._state.get("depth", 0) or 0),
                    energy=float(self._state.get("energy", 0.0) or 0.0),
                    payload=self._payload(),
                )
                budget = self._budget_event()
                if budget is not None:
                    yield budget

            snapshot = await self._graph.aget_state(self._graph_config)
            pending = tuple(getattr(snapshot, "next", ()) or ())
            if "steer" in pending:
                yield Waiting(reason="steer")
                return

            # If no surface tokens streamed, persist the best final-answer field.
            if not self._answered:
                answer = self._state.get("surfaced_insight") or self._state.get("synthesis") or ""
                if answer:
                    yield Token(text=answer)

            yield Complete(
                stop_reason=str(self._state.get("stop_reason") or "ended"),
                status="done",
            )
        except Exception as exc:  # surface engine failures as a terminal event
            yield Complete(stop_reason=f"error: {exc}", status="error")


def build_ouroboros_graph(
    *,
    thread_id: str,
    groq_api_key: str,
    groq_model: str = "llama-3.3-70b-versatile",
    mode: str = "analyze",
    adaptive: bool = True,
    compute_budget: int = 6,
    temperature: float = 0.7,
    stability_threshold: float | None = None,
    confidence_threshold: float | None = None,
    steer_interval: int | None = None,
    adaptive_steer: bool = False,
):
    """Construct a real, isolated Ouroboros graph + the wiring the producer needs.

    Returns ``(graph, graph_config, make_inputs, usage_reader)``.

    Settings isolation (gotcha a): the LLM is built here from an explicit Groq key
    and passed into `create_ouroboros_graph`, so the engine never calls Ouroboros's
    `get_settings()` / `load_dotenv()` and never inherits Helix's ambient `.env`
    (whose `LLM_PROVIDER=stub` is invalid for Ouroboros's `groq|openai|ollama`
    enum — gotcha b). The adaptive convergence controller is ON by default (the
    principled budget/halting story).
    """
    # Lazy imports: the heavy LangGraph/LangChain stack loads only when deep
    # reasoning is actually invoked, and only the vendored engine is touched.
    from engine.ouroboros_bootstrap import load_ouroboros

    ouroboros = load_ouroboros()
    from langchain_groq import ChatGroq

    Mode = ouroboros.models.Mode
    MODE_PRESETS = ouroboros.presets.MODE_PRESETS
    create_ouroboros_graph = ouroboros.graph.create_ouroboros_graph
    new_usage_handler = ouroboros.usage.new_usage_handler
    summarize_usage = ouroboros.usage.summarize_usage

    mode_enum = Mode(mode) if mode in [m.value for m in Mode] else Mode.ANALYZE
    overrides: dict[str, Any] = {
        "adaptive": adaptive,
        "compute_budget": compute_budget,
        "temperature": temperature,
        # Helix surfaces answers to a human in chat: rewrite the converged synthesis
        # into a warm, conversational, streamed final answer (the benchmark leaves
        # this off to preserve raw-synthesis output parity).
        "humanize": True,
        # Guided mode: pause the adaptive loop at the steer checkpoint between
        # refinement cycles so the caller can inject guidance over HTTP.
        "adaptive_steer": adaptive_steer,
    }
    # Convergence thresholds are tunable so the controller can halt on a real
    # `converged` / `no_marginal_gain` signal (the answer has stopped moving)
    # rather than always exhausting the budget. `None` auto-calibrates to the
    # active embedder: neural MiniLM cosines between successive drafts of the
    # same answer sit far higher than the lexical fallback's token-overlap
    # scores, so a lexical-calibrated threshold would halt neural runs on the
    # first refinement.
    if stability_threshold is None:
        embedder_name = getattr(ouroboros.memory.get_embedder(), "name", "lexical-fallback")
        stability_threshold = 0.78 if embedder_name.startswith("lexical") else 0.90
    overrides["stability_threshold"] = stability_threshold
    if confidence_threshold is not None:
        overrides["confidence_threshold"] = confidence_threshold
    if steer_interval is not None:
        # Non-adaptive runs pause for human steer every `steer_interval` cycles;
        # a small value makes a steer demo pause promptly instead of after many cycles.
        overrides["steer_interval"] = steer_interval
    cfg = MODE_PRESETS[mode_enum]["config"].model_copy(update=overrides)

    llm = ChatGroq(model=groq_model, temperature=temperature, api_key=groq_api_key or None)
    graph = create_ouroboros_graph(llm, cfg)

    usage_handler = new_usage_handler()
    graph_config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [usage_handler],
    }

    def make_inputs(seed: str) -> dict[str, Any]:
        # Mirrors server.py's initial OuroborosState.
        return {
            "messages": [],
            "thought": seed,
            "seed": seed,
            "mood": "curious",
            "energy": cfg.starting_energy,
            "depth": 0,
            "memories": [],
            "insights": [],
            "emotional_reading": "",
            "logical_reading": "",
            "memory_reading": "",
            "synthesis": "",
            "loop_guard": 0,
            "tick": 0,
            "surfaced_insight": "",
            "mode": cfg.mode.value,
            "research_queries": [],
            "research_findings": [],
            "human_input": "",
            "steer_count": 0,
        }

    def usage_reader() -> int:
        return int(summarize_usage(usage_handler).get("total_tokens", 0))

    return graph, graph_config, make_inputs, usage_reader
