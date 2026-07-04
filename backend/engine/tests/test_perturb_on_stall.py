"""Perturb-on-stall: a stable-but-unconfident answer gets stress-tested once
before the loop is allowed to halt on stability alone. Repetition is weak
evidence; surviving an attack is real evidence.
"""
from __future__ import annotations

from ouroboros.graph.controller import decide
from ouroboros.graph.nodes import _synthesize_adaptive, make_think, steer
from ouroboros.models import OuroborosConfig

CFG = OuroborosConfig(
    adaptive=True,
    min_cycles=1,
    compute_budget=6,
    stability_threshold=0.9,
    confidence_threshold=0.75,
)


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.prompts: list[str] = []

    async def ainvoke(self, messages):
        self.prompts.append(messages[0]["content"])
        return FakeResponse(self.reply)


# --- the controller's decision table ------------------------------------------

def test_stable_unconfident_first_stall_perturbs_instead_of_halting():
    d = decide(depth=2, stability=0.95, confidence=0.5, config=CFG, perturbed=False)
    assert (d.halt, d.reason) == (False, "perturb")


def test_stable_unconfident_after_challenge_halts_honestly():
    d = decide(depth=3, stability=0.95, confidence=0.5, config=CFG, perturbed=True)
    assert (d.halt, d.reason) == (True, "no_marginal_gain")


def test_stable_and_confident_converges_with_or_without_perturbation():
    for perturbed in (False, True):
        d = decide(depth=2, stability=0.95, confidence=0.9, config=CFG, perturbed=perturbed)
        assert (d.halt, d.reason) == (True, "converged")


def test_budget_still_caps_everything():
    d = decide(depth=6, stability=0.95, confidence=0.5, config=CFG, perturbed=False)
    assert (d.halt, d.reason) == (True, "budget")


# --- the loop mechanics --------------------------------------------------------

def _state(**over):
    base = {"seed": "q?", "synthesis": "", "depth": 1, "messages": []}
    base.update(over)
    return base


async def test_synthesize_issues_one_challenge_then_halts_on_second_stall():
    # Same answer, low confidence -> stability 1.0, below confidence gate.
    llm = FakeLLM("The answer is X.\nCONFIDENCE: 0.4")
    first = await _synthesize_adaptive(
        llm, CFG, _state(prev="ignored", synthesis="The answer is X."), "", "", ""
    )
    assert first["stop_reason"] == "perturb"
    assert first["should_halt"] is False
    assert first["perturbed"] is True
    assert first["challenge"]  # a concrete instruction rides to the next think

    second = await _synthesize_adaptive(
        llm, CFG, _state(synthesis="The answer is X.", perturbed=True), "", "", ""
    )
    assert second["stop_reason"] == "no_marginal_gain"
    assert second["should_halt"] is True


async def test_think_consumes_the_challenge_and_attacks_the_answer():
    cfg = OuroborosConfig(adaptive=True)
    llm = FakeLLM("The weakest assumption is Y.")
    think = make_think(llm, cfg)
    out = await think(
        _state(
            synthesis="The answer is X.",
            challenge="Stress-test it: what breaks it?",
            memories=[],
        )
    )
    assert out["challenge"] == ""  # consumed exactly once
    prompt = llm.prompts[0]
    assert "stress-testing" in prompt.lower()
    assert "The answer is X." in prompt
    assert "what breaks it?" in prompt


def test_human_steer_supersedes_a_pending_challenge():
    out = steer(_state(human_input="focus on cost instead", challenge="attack!"))
    assert out["thought"] == "focus on cost instead"
    assert out["challenge"] == ""
