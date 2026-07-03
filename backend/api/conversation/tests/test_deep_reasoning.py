"""Tests for the DeepReasoningProducer (E3) against a fake Ouroboros-shaped graph.

No LangGraph/Ouroboros import — the producer is pure event-mapping, so a fake
graph that yields the same `(mode, data)` tuples proves the contract:
Step/Budget for the trace, Token for the final (`surface`) answer only, Waiting
on a steer interrupt, Complete at the end. Also runs through `engine.send` to
prove the second producer drops into the same orchestrator as chat.
"""
from types import SimpleNamespace

from api.conversation.deep_reasoning import DeepReasoningProducer
from api.conversation.engine import send
from api.conversation.events import (
    AssistantNode,
    Budget,
    Complete,
    Done,
    Step,
    Token,
    UserNode,
    Waiting,
)
from api.conversation.store import InMemoryStore


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeGraph:
    """Yields canned `astream` tuples; `next_` drives the steer-interrupt check."""

    def __init__(self, events, next_=()):
        self._events = events
        self._next = next_

    async def astream(self, inputs, config, stream_mode):
        for ev in self._events:
            yield ev

    async def aget_state(self, config):
        return SimpleNamespace(next=self._next)


_RUN_EVENTS = [
    ("updates", {"think": {"depth": 1, "energy": 75.0, "thought": "first thought"}}),
    ("updates", {"synthesize": {"synthesis": "draft", "confidence": 0.6, "stability": 0.5}}),
    ("messages", (_Chunk("Final "), {"langgraph_node": "surface"})),
    ("messages", (_Chunk("answer."), {"langgraph_node": "surface"})),
    ("updates", {"surface": {"surfaced_insight": "Final answer.", "stop_reason": "converged"}}),
    # A non-surface token must NOT leak into the persisted answer.
    ("messages", (_Chunk("inner monologue"), {"langgraph_node": "think"})),
]


def _producer(events, next_=(), **kw):
    return DeepReasoningProducer(graph=FakeGraph(events, next_), graph_config={}, **kw)


async def _branch():
    store = InMemoryStore()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="u1", title="t", visibility="shared"
    )
    return store, conv.default_branch_id


async def _node(content="why?"):
    """A store + branch with one user node already on it (for producer-only tests)."""
    store, branch_id = await _branch()
    n = await store.add_node(branch_id=branch_id, role="user", content=content, author_id="u1")
    return store, branch_id, [n]


async def test_maps_steps_tokens_and_completes():
    _, _, history = await _node()
    counter = {"n": 0}

    def usage_reader():
        counter["n"] += 100
        return counter["n"]

    events = [e async for e in _producer(_RUN_EVENTS, usage_reader=usage_reader, token_budget=1000).run(history)]

    steps = [e for e in events if isinstance(e, Step)]
    assert [s.node for s in steps] == ["think", "synthesize", "surface"]
    assert steps[0].depth == 1 and steps[0].energy == 75.0

    # Only the surface node's tokens are relayed for persistence.
    assert [t.text for t in events if isinstance(t, Token)] == ["Final ", "answer."]

    budgets = [e for e in events if isinstance(e, Budget)]
    assert budgets and budgets[-1].tokens_budget == 1000
    assert budgets[-1].pct == round(budgets[-1].tokens_used / 1000, 4)

    assert isinstance(events[-1], Complete)
    assert events[-1].status == "done" and events[-1].stop_reason == "converged"


async def test_steps_carry_the_stability_threshold_from_config_metadata():
    """The resolved convergence target rides on every step payload (monitor viz)."""
    _, _, history = await _node()
    producer = DeepReasoningProducer(
        graph=FakeGraph(_RUN_EVENTS),
        graph_config={"metadata": {"stability_threshold": 0.9}},
    )
    steps = [e async for e in producer.run(history) if isinstance(e, Step)]
    assert steps and all(s.payload["stability_threshold"] == 0.9 for s in steps)

    # Without metadata (the fakes' default), the key is simply absent.
    bare = [e async for e in _producer(_RUN_EVENTS).run(history) if isinstance(e, Step)]
    assert all("stability_threshold" not in s.payload for s in bare)


async def test_waiting_on_steer_interrupt():
    _, _, history = await _node()
    events = [e async for e in _producer(_RUN_EVENTS, next_=("steer",)).run(history)]
    assert isinstance(events[-1], Waiting)
    assert not any(isinstance(e, Complete) for e in events)


class SteerableGraph:
    """A two-phase fake graph: pauses at `steer`, then resumes to completion.

    Phase 1 (`astream(inputs=...)`) yields one step and leaves a pending `steer`.
    After `aupdate_state` injects human input, phase 2 (`astream(inputs=None)`)
    yields the steered step, the surface answer, and converges.
    """

    def __init__(self):
        self._phase = 0
        self.injected = None

    async def astream(self, inputs, config, stream_mode):
        if self._phase == 0:
            yield ("updates", {"think": {"depth": 1, "energy": 80.0, "thought": "stuck"}})
            self._phase = 1
        else:
            yield ("updates", {"steer": {"thought": f"using: {self.injected}"}})
            yield ("messages", (_Chunk("Steered answer."), {"langgraph_node": "surface"}))
            yield ("updates", {"surface": {"surfaced_insight": "Steered answer.", "stop_reason": "converged"}})
            self._phase = 2

    async def aupdate_state(self, config, values):
        self.injected = values.get("human_input")

    async def aget_state(self, config):
        return SimpleNamespace(next=("steer",) if self._phase == 1 else ())


async def test_steer_pause_then_resume_to_completion():
    """P4: pause on steer -> inject human_input -> resume on the same thread."""
    _, _, history = await _node()
    graph = SteerableGraph()
    producer = DeepReasoningProducer(graph=graph, graph_config={"configurable": {"thread_id": "t1"}})

    first = [e async for e in producer.run(history)]
    assert isinstance(first[-1], Waiting)  # paused, no Complete yet
    assert not any(isinstance(e, Complete) for e in first)
    first_steps = [e for e in first if isinstance(e, Step)]

    resumed = [e async for e in producer.resume("focus on cost")]
    assert graph.injected == "focus on cost"  # human input reached the graph
    # The step counter carried over across the pause.
    resumed_steps = [e for e in resumed if isinstance(e, Step)]
    assert resumed_steps[0].idx == first_steps[-1].idx + 1
    # The resumed run produced the final answer and converged.
    assert [t.text for t in resumed if isinstance(t, Token)] == ["Steered answer."]
    assert isinstance(resumed[-1], Complete)
    assert resumed[-1].status == "done" and resumed[-1].stop_reason == "converged"


async def test_falls_back_to_surfaced_insight_when_no_surface_tokens():
    _, _, history = await _node()
    events = [
        ("updates", {"synthesize": {"synthesis": "the synthesis"}}),
        ("updates", {"surface": {"surfaced_insight": "Crystallized answer."}}),
    ]
    out = [e async for e in _producer(events).run(history)]
    tokens = [t.text for t in out if isinstance(t, Token)]
    assert tokens == ["Crystallized answer."]  # surfaced_insight wins as the answer


async def test_kill_stops_run_and_marks_killed():
    _, _, history = await _node()
    # Stop after the first event is processed.
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 1

    out = [e async for e in _producer(_RUN_EVENTS, should_stop=should_stop).run(history)]

    assert isinstance(out[-1], Complete)
    assert out[-1].status == "killed" and out[-1].stop_reason == "stopped"
    # Killed early: not all three steps were emitted.
    assert len([e for e in out if isinstance(e, Step)]) < 3


async def test_seeds_over_thread_context_not_just_last_line():
    """P2: the producer reasons over the inherited thread, not one isolated line."""
    store, branch_id = await _branch()
    await store.add_node(
        branch_id=branch_id, role="user", content="we're choosing a cache layer", author_id="u1"
    )
    await store.add_node(
        branch_id=branch_id, role="assistant", content="Redis or in-memory?", author_id=None
    )
    await store.add_node(
        branch_id=branch_id, role="user", content="which fits a single instance?", author_id="u2"
    )
    history = await store.get_history(branch_id)

    captured = {}

    def capturing_make_inputs(seed):
        captured["seed"] = seed
        return {"seed": seed, "thought": seed}

    [e async for e in _producer(_RUN_EVENTS, make_inputs=capturing_make_inputs).run(history)]

    assert "which fits a single instance?" in captured["seed"]  # the question
    assert "choosing a cache layer" in captured["seed"]  # prior context carried in


async def test_runs_through_engine_send_and_persists_final_answer():
    store, branch_id = await _branch()  # send() adds the user node itself
    producer = _producer(_RUN_EVENTS)

    events = [
        e async for e in send(
            store=store, producer=producer, branch_id=branch_id, prompt="why?", author_id="u1"
        )
    ]

    # Same orchestration bracket as chat: UserNode ... AssistantNode, Done.
    assert isinstance(events[0], UserNode)
    assert isinstance(events[-1], Done)
    assert isinstance(events[-2], AssistantNode)
    # The deep-reasoning trace rode through untouched.
    assert any(isinstance(e, Step) for e in events)
    assert any(isinstance(e, Complete) for e in events)
    # The persisted assistant answer is the surface text, not the inner monologue.
    assert events[-2].node.content == "Final answer."

    history = await store.get_history(branch_id)
    assert [(n.role, n.content) for n in history] == [
        ("user", "why?"),
        ("assistant", "Final answer."),
    ]
