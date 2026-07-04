"""Metacognitive controller: content-aware halting for adaptive test-time compute.

This is the research wedge (see docs/RESEARCH.md). Standard reflection loops spend
a *fixed* amount of compute — N iterations, a depth cap, or (as in this engine's
legacy router) a coin flip. The controller replaces that with a principled stop
decision driven by cheap internal signals:

- **answer stability** — semantic convergence between successive refined answers
  (cosine over the same embedder used for semantic memory). High stability means
  the loop has stopped changing its mind: more cycles buy little.
- **self-confidence** — the synthesizer's own 0-1 estimate of how settled its
  answer is.

Bounded by a compute budget, this spends more cycles on hard / still-moving
problems and halts early on ones that have already converged. Because halting
early stops wasting tokens, the same mechanism is what keeps the engine inside
free-tier rate limits — the product virtue and the research claim are one thing.
"""

from __future__ import annotations

from dataclasses import dataclass

import re

from ouroboros.memory import _word_chunks, cosine_similarity, get_embedder
from ouroboros.models import OuroborosConfig

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    """Sentence-ish units for localized-change detection; short fragments are
    dropped (headings, list numbers) so they can't fabricate instability."""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text)]
    return [p for p in parts if len(p) >= 20]


def answer_stability(prev: str, curr: str) -> float:
    """How settled the answer is between two successive drafts (1.0 = unchanged).

    Short drafts (a single embedding chunk): plain cosine similarity over the
    shared embedder (works offline via the lexical fallback).

    Long drafts: whole-text pooling dilutes a localized change — one flipped
    conclusion inside a long answer barely moves the mean vector (measured:
    0.976 pooled cosine for a hard contradiction past the old truncation
    point). So the pooled similarity is *blended* with a localized floor: every
    sentence of each draft is matched to its most similar sentence in the other
    draft, and the least-anchored sentence (bidirectional — additions and
    deletions both count) sets the floor. A genuine meaning flip drags the
    blend below the halting threshold and buys another refine cycle; mere
    rewording recovers on the next cycle once the wording settles.

    Returns 0.0 if either side is empty (first cycle: nothing to compare).
    """
    if not prev or not curr:
        return 0.0
    embedder = get_embedder()
    if len(_word_chunks(prev)) == 1 and len(_word_chunks(curr)) == 1:
        a, b = embedder.embed([prev, curr])
        return max(0.0, min(1.0, cosine_similarity(a, b)))

    pooled_prev, pooled_curr = embedder.embed([prev, curr])
    pooled = cosine_similarity(pooled_prev, pooled_curr)

    prev_sents, curr_sents = _sentences(prev), _sentences(curr)
    if not prev_sents or not curr_sents:
        return max(0.0, min(1.0, pooled))
    vectors = embedder.embed(prev_sents + curr_sents)
    prev_vecs, curr_vecs = vectors[: len(prev_sents)], vectors[len(prev_sents) :]

    def _least_anchored(side: list[list[float]], other: list[list[float]]) -> float:
        return min(max(cosine_similarity(v, o) for o in other) for v in side)

    floor = min(_least_anchored(curr_vecs, prev_vecs), _least_anchored(prev_vecs, curr_vecs))
    return max(0.0, min(1.0, (pooled + floor) / 2))


@dataclass(frozen=True)
class Decision:
    """A halting decision plus the reason, for routing and interpretability."""

    halt: bool
    reason: str


def decide(
    *,
    depth: int,
    stability: float,
    confidence: float,
    config: OuroborosConfig,
    perturbed: bool = False,
) -> Decision:
    """Decide whether to stop refining, from internal signals + the budget.

    Pure function of scalars (no LLM, no embedding) so it is fully unit-testable.
    Precedence: honour ``min_cycles`` first, then the hard ``compute_budget`` cap,
    then convergence (stable *and* confident).

    Stable-but-unconfident is the suspicious case: the answer stopped moving,
    but the model won't vouch for it — which is what a loop that is *stuck*
    (confidently wrong, or circling) looks like, not just one that is done.
    Halting there ships the stuck answer. So the first time it happens the
    controller returns a ``perturb`` decision instead: the next cycle
    stress-tests the answer, and only convergence *after* the challenge (or a
    second stall, ``perturbed=True``) is accepted. Repetition is weak evidence;
    surviving an attack is real evidence.
    """
    if depth < config.min_cycles:
        return Decision(False, "min_cycles")
    if depth >= config.compute_budget:
        return Decision(True, "budget")
    if (
        stability >= config.stability_threshold
        and confidence >= config.confidence_threshold
    ):
        return Decision(True, "converged")
    if stability >= config.stability_threshold:
        if not perturbed:
            return Decision(False, "perturb")
        return Decision(True, "no_marginal_gain")
    return Decision(False, "continue")
