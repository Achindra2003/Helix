"""Harness self-test: the full experiment loop against fakes — no network, no
keys. Proves the machinery (arms → runs → judging → aggregation → report)
before any tokens are spent on it.
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.harness import ARMS, _load_questions, render_report, run_experiment, summarize
from evals.judge import Judgment, parse_judgment

QUESTIONS = [
    {"id": "q-easy", "tier": "easy", "question": "Pick a database."},
    {"id": "q-hard", "tier": "hard", "question": "Design a feed."},
]


class _FakeGraph:
    """Terminates at min(budget, 3) cycles like a converging run would."""

    def __init__(self, budget: int, min_cycles: int):
        self.cycles = min(budget, 3) if min_cycles < budget else budget

    async def ainvoke(self, inputs, config):
        return {
            "surfaced_insight": f"answer after {self.cycles} cycles",
            "depth": self.cycles,
            "stop_reason": "budget",
        }


def _fake_factory(**kw):
    graph = _FakeGraph(kw["compute_budget"], kw["min_cycles"])
    usage = {"tokens": 900 * graph.cycles}
    return graph, {}, lambda seed: {"seed": seed}, lambda: usage["tokens"]


async def _fake_judge(question: str, answer: str) -> Judgment:
    return Judgment(7.5, "fine")


async def test_experiment_runs_all_cells_and_aggregates():
    results = await run_experiment(
        QUESTIONS,
        ["fixed-1", "adaptive"],
        graph_factory=_fake_factory,
        judge=_fake_judge,
        model="fake-model",
        api_key="fake",
    )
    assert len(results) == 4  # 2 questions × 2 arms
    assert all(r.score == 7.5 for r in results)
    # fixed-1 pinned to exactly one cycle; adaptive "converged" at 3.
    assert {r.depth for r in results if r.arm == "fixed-1"} == {1}
    assert {r.depth for r in results if r.arm == "adaptive"} == {3}

    summaries = summarize(results)
    by_arm = {s.arm: s for s in summaries}
    assert by_arm["fixed-1"].mean_tokens == 900
    assert by_arm["adaptive"].mean_tokens == 2700

    report = render_report(results, summaries, model="fake-model", judge_model="fake-judge")
    assert "| fixed-1 | 2 | 7.5 | 900 | 1 | budget×2 |" in report
    assert "## Per-tier mean score" in report


async def test_a_failing_run_is_recorded_not_fatal():
    def _exploding_factory(**kw):
        class _Boom:
            async def ainvoke(self, inputs, config):
                raise RuntimeError("provider down")

        return _Boom(), {}, lambda seed: {"seed": seed}, lambda: 0

    results = await run_experiment(
        QUESTIONS[:1],
        ["fixed-1"],
        graph_factory=_exploding_factory,
        judge=_fake_judge,
        model="fake",
        api_key="fake",
    )
    assert results[0].error.startswith("RuntimeError")
    assert results[0].score is None
    assert summarize(results) == []  # unscored runs never fabricate a mean


def test_judgment_parsing_is_strict_but_tolerant_of_wrapping():
    ok = parse_judgment('Sure! {"score": 8, "justification": "solid"} hope that helps')
    assert ok.score == 8.0 and ok.justification == "solid"
    assert parse_judgment('{"score": 14}').score == 10.0  # clamped
    assert parse_judgment("I refuse to answer in JSON").score is None


def test_question_subset_is_tier_balanced(tmp_path: Path):
    payload = {
        "questions": [
            {"id": f"{tier}-{i}", "tier": tier, "question": "?"}
            for tier in ("easy", "medium", "hard")
            for i in range(6)
        ]
    }
    path = tmp_path / "q.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    picked = _load_questions(path, 6)
    assert len(picked) == 6
    assert {q["tier"] for q in picked} == {"easy", "medium", "hard"}


def test_declared_arms_are_well_formed():
    for name, cfg in ARMS.items():
        assert cfg["min_cycles"] <= cfg["compute_budget"], name
