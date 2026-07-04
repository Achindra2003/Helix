"""Regression tests for the adaptive-synthesis answer extraction.

The synthesize model was told to output *only* an improved answer, but in practice
it emits a critique paragraph then a labelled answer ("IMPROVED answer: ..."). If
the whole blob is kept, convergence is measured on the critique and the humanized
final answer is skewed toward critique artifacts ("emotional burden", "team
morale"). `_strip_answer_label` keeps only the answer; these lock that in.
"""
from engine.ouroboros_bootstrap import load_ouroboros

load_ouroboros()
from ouroboros.graph.nodes import _parse_confidence, _strip_answer_label  # noqa: E402


def _clean(raw: str) -> str:
    answer, _conf, _reported = _parse_confidence(raw.strip())
    return _strip_answer_label(answer)


def test_strips_critique_and_label():
    raw = (
        "The current answer overlooks the potential emotional burden and technical "
        "debt of a custom solution.\n\n"
        'IMPROVED answer:\n"Use Auth0 for a 4-person team; the maintenance cost of '
        'custom auth is not worth it unless you have a hard compliance requirement."\n'
        "CONFIDENCE: 0.9"
    )
    answer = _clean(raw)
    assert answer.startswith("Use Auth0")
    assert "overlooks" not in answer
    assert "IMPROVED" not in answer
    assert '"' not in answer  # wrapping quotes removed


def test_leaves_clean_answer_untouched():
    raw = "Use Auth0. For a small team the maintenance burden of custom auth isn't worth it."
    assert _clean(raw) == raw


def test_handles_various_labels():
    for label in ("Revised answer:", "Final Answer :", "the better answer:"):
        raw = f"Some critique here.\n{label} Go with Auth0."
        assert _clean(raw) == "Go with Auth0."
