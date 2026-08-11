"""Every mode is a complete preset, and its prompts survive being formatted.

The Review preset is what prompted these, but none of them are about Review:
they are the three ways adding *any* mode fails quietly.

A mode with no preset does not crash — `_get_prompt` falls back to Explore — so
it runs somebody else's prompts under its own name for as long as nobody looks.
A prompt naming a placeholder its node does not supply raises `KeyError` inside
the node, where the fallback catches it and returns a canned thought, so the run
completes and the reasoning is silently gone. And the two mode lists hard-coded
in `nodes.py` decide what a mode *is* as much as its prompts do; a new mode
lands on the default side of both by omission.
"""
from __future__ import annotations

import asyncio

from ouroboros.graph.nodes import make_emotional_analysis, make_reflect, make_think
from ouroboros.models import Mode, OuroborosConfig
from ouroboros.presets import MODE_PRESETS


# The kwargs each node actually passes to `.format()`. Kept here as data so a
# prompt can be checked without running the graph — see nodes.make_think,
# make_reflect and make_surface.
FORMAT_ARGS = {
    "think_prompt": {
        "mood": "curious", "depth": 1, "recent": "r", "memories": "m", "seed": "s",
    },
    "reflect_prompt": {"thought": "t", "mood": "curious", "seed": "s"},
    "surface_prompt": {"depth": 1, "seed": "s", "thought": "t"},
}


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    """Records the prompt it was handed. Nothing here needs a real answer."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, messages):
        self.prompts.append(messages[0]["content"])
        return FakeResponse("ok")


def test_every_mode_has_its_own_preset():
    """`_get_prompt` falls back to Explore for an unknown mode, so a missing
    preset is invisible: the run works, and thinks like a different mode."""
    assert set(MODE_PRESETS) == set(Mode)


def test_every_preset_carries_the_whole_shape():
    for mode, preset in MODE_PRESETS.items():
        assert preset["label"], mode
        assert len(preset["description"]) > 25, mode
        assert preset["config"].mode is mode, mode
        for key in FORMAT_ARGS:
            assert preset[key].strip(), f"{mode} has no {key}"


def test_every_prompt_formats_with_exactly_what_its_node_supplies():
    """A prompt naming `{diff}` or `{findings}` raises KeyError in the node —
    which catches it and substitutes a canned fallback, so the run "succeeds"
    with the reasoning quietly replaced."""
    for mode, preset in MODE_PRESETS.items():
        for key, args in FORMAT_ARGS.items():
            try:
                rendered = preset[key].format(**args)
            except KeyError as exc:  # pragma: no cover - the failure we're pinning
                raise AssertionError(
                    f"{mode.value}.{key} wants {exc} and its node does not pass it"
                ) from exc
            assert "{" not in rendered, f"{mode.value}.{key} left a brace unfilled"


def test_review_gets_the_human_perspective_not_the_couch():
    """The `emotional` analysis branches on a hard-coded list of practical modes.
    A review run's thought is a defect report about someone else's work; on the
    default branch the node asks what that thought "is avoiding, or yearning
    toward" — i.e. it psychoanalyses the author."""
    llm = FakeLLM()
    node = make_emotional_analysis(llm, MODE_PRESETS[Mode.REVIEW]["config"])
    asyncio.run(node({"thought": "the retry loop swallows the timeout", "mode": "review"}))

    prompt = llm.prompts[0]
    assert "human perspective" in prompt
    assert "yearning" not in prompt


def test_review_prompts_ask_for_severity_and_forbid_a_summary():
    """The preset's whole job. Ranked findings are what makes a review usable;
    a restatement of the change is what makes one worthless."""
    preset = MODE_PRESETS[Mode.REVIEW]
    think = preset["think_prompt"].format(**FORMAT_ARGS["think_prompt"]).lower()
    assert "blocking" in think and "minor" in think
    assert "do not summarise" in think


def test_review_is_paced_like_the_other_rigorous_modes():
    """Same guardrails, not gentler ones — a preset that quietly ran deeper or
    paused less often would be a budget exception wearing a mode's clothes."""
    review = MODE_PRESETS[Mode.REVIEW]["config"]
    analyze = MODE_PRESETS[Mode.ANALYZE]["config"]

    assert review.steer_interval == analyze.steer_interval
    assert review.max_depth <= analyze.max_depth
    assert review.starting_energy == analyze.starting_energy
    # Mood steers the emotional reading and (non-adaptive) the surfacing route.
    # A reviewer whose temper drifts mid-pass ranks the same defect differently.
    assert review.mood_shift_chance <= analyze.mood_shift_chance


def test_a_review_run_uses_the_review_prompts():
    """End of the wiring: preset -> config -> node. `make_think` resolves its
    template once at build time from `config.mode`, so this is what proves the
    mode reaches the model rather than only the config object."""
    cfg = MODE_PRESETS[Mode.REVIEW]["config"].model_copy(update={"adaptive": True})
    llm = FakeLLM()
    think = make_think(llm, cfg)
    asyncio.run(think({
        "messages": [], "memories": [], "seed": "does this patch do what the issue asked?",
        "mood": "curious", "depth": 0, "energy": cfg.starting_energy,
    }))
    assert "reviewing the work" in llm.prompts[0]

    llm2 = FakeLLM()
    reflect = make_reflect(llm2, cfg)
    asyncio.run(reflect({"thought": "the retry loop swallows the timeout"}))
    assert "defect or a preference" in llm2.prompts[0]


def test_config_defaults_still_hold_for_the_new_mode():
    """`OuroborosConfig` validates its ranges; a preset that violated one would
    fail at import, but only if something constructs it."""
    assert OuroborosConfig(mode=Mode.REVIEW).mode is Mode.REVIEW
