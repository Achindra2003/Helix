"""The convergence signal must be honest: transient provider failures retry,
hard failures halt with their own stop reason (never a fake convergence), and
an unreported confidence never counts toward "converged".
"""
from __future__ import annotations

import pytest

from ouroboros.graph.nodes import (
    _ainvoke_with_retry,
    _is_retryable,
    _parse_confidence,
    _synthesize_adaptive,
)
from ouroboros.models import OuroborosConfig


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    """Scripted LLM: each item is either a reply string or an exception."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


# --- _parse_confidence -------------------------------------------------------

def test_parse_confidence_with_marker():
    answer, conf, reported = _parse_confidence("Use Postgres.\nCONFIDENCE: 0.85")
    assert answer == "Use Postgres."
    assert conf == 0.85
    assert reported is True


def test_parse_confidence_repairs_bare_number_last_line():
    answer, conf, reported = _parse_confidence("Use Postgres.\n0.7")
    assert answer == "Use Postgres."
    assert conf == 0.7
    assert reported is True


def test_parse_confidence_missing_marker_is_flagged_placeholder():
    answer, conf, reported = _parse_confidence("Use Postgres, definitely.")
    assert answer == "Use Postgres, definitely."
    assert conf == 0.5
    assert reported is False


def test_parse_confidence_never_eats_a_one_line_numeric_answer():
    # A single line that IS the answer (e.g. "42") must not be consumed as a rating.
    answer, conf, reported = _parse_confidence("0.9")
    assert answer == "0.9"
    assert reported is False


# --- retry policy ------------------------------------------------------------

def test_retryable_classification():
    assert _is_retryable(RuntimeError("429 Too Many Requests"))
    assert _is_retryable(RuntimeError("rate limit exceeded, try later"))
    assert _is_retryable(ConnectionError("connection reset"))
    assert not _is_retryable(ValueError("model rejected the prompt"))


async def test_transient_failure_retries_then_succeeds():
    llm = FakeLLM([RuntimeError("429 rate limit"), RuntimeError("503"), "recovered"])
    resp = await _ainvoke_with_retry(llm, [], base_delay=0.001)
    assert resp.content == "recovered"
    assert llm.calls == 3


async def test_non_retryable_failure_raises_immediately():
    llm = FakeLLM([ValueError("bad request"), "never reached"])
    with pytest.raises(ValueError):
        await _ainvoke_with_retry(llm, [], base_delay=0.001)
    assert llm.calls == 1


async def test_retries_exhausted_reraises():
    llm = FakeLLM([RuntimeError("429")] * 4)
    with pytest.raises(RuntimeError):
        await _ainvoke_with_retry(llm, [], attempts=4, base_delay=0.001)
    assert llm.calls == 4


# --- provider-failure honesty in the adaptive synthesizer ---------------------

def _state(prev: str = "", **over):
    base = {"seed": "q?", "synthesis": prev, "depth": 0, "messages": []}
    base.update(over)
    return base


async def test_provider_failure_halts_honestly_not_as_convergence():
    """The old bug: on failure, answer=prev made stability(prev,prev)==1.0 and
    the run halted "no_marginal_gain" — a rate-limit blip wearing a converged
    face. It must halt with its own stop reason and untouched signals."""
    cfg = OuroborosConfig(adaptive=True, min_cycles=1)
    llm = FakeLLM([ValueError("provider exploded")])
    out = await _synthesize_adaptive(
        llm, cfg, _state(prev="the previous answer", stability=0.4, confidence=0.6),
        "", "", "",
    )
    assert out["should_halt"] is True
    assert out["stop_reason"] == "provider_error"
    assert "provider exploded" in out["provider_error"]
    assert out["synthesis"] == "the previous answer"  # best effort preserved
    assert out["stability"] == 0.4  # prior signal carried, not invented
    assert out["confidence_reported"] is False


async def test_unreported_confidence_cannot_satisfy_the_convergence_gate():
    """Identical successive answers (stability 1.0) with NO confidence marker:
    with a low confidence threshold the placeholder 0.5 would count as
    "converged" — it must not. Stability alone still halts, but the reason is
    the honest one."""
    cfg = OuroborosConfig(
        adaptive=True, min_cycles=1, stability_threshold=0.9, confidence_threshold=0.4
    )
    llm = FakeLLM(["The answer is X."])  # no CONFIDENCE line
    out = await _synthesize_adaptive(llm, cfg, _state(prev="The answer is X."), "", "", "")
    assert out["stability"] >= 0.9
    assert out["confidence_reported"] is False
    assert out["stop_reason"] != "converged"


async def test_reported_confidence_converges_normally():
    cfg = OuroborosConfig(
        adaptive=True, min_cycles=1, stability_threshold=0.9, confidence_threshold=0.7
    )
    llm = FakeLLM(["The answer is X.\nCONFIDENCE: 0.9"])
    out = await _synthesize_adaptive(llm, cfg, _state(prev="The answer is X."), "", "", "")
    assert out["stop_reason"] == "converged"
    assert out["confidence"] == 0.9
    assert out["confidence_reported"] is True
