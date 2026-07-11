"""Okapi BM25 — the lexical half of hybrid retrieval.

Dense vectors match paraphrase ("how do we roll back a deploy?" finds the
runbook that never says "roll back"); they are weak on exact rare terms
(error codes, env-var names, ticket ids) where the embedding of `ZX-9931`
carries almost no signal. BM25 is the mirror image: exact-term precision,
no paraphrase. Hybrid retrieval runs both and fuses (see service.py).

Implemented in ~60 lines instead of importing rank_bm25: workspace corpora
are small (the pgvector note in service.py bounds them), scoring a few
hundred chunks per query is microseconds, and the point of this codebase is
that the mechanics are readable. Standard Okapi parameters (k1=1.5, b=0.75).
"""
from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_\-\.]*")


def tokenize(text: str) -> list[str]:
    """Lowercased word-ish tokens. Keeps `_`, `-`, `.` inside tokens so
    identifiers (`retry_count`, `v1.2`, `ZX-9931`) survive as exact terms —
    they are precisely what lexical retrieval exists to match."""
    return _TOKEN.findall(text.lower())


class BM25:
    """Okapi BM25 over a fixed corpus (rebuild per query set — no index state)."""

    def __init__(self, corpus: list[str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._docs = [tokenize(text) for text in corpus]
        self._doc_len = [len(d) for d in self._docs]
        self._avg_len = (sum(self._doc_len) / len(self._docs)) if self._docs else 0.0
        # Document frequency per term -> smoothed idf (the +0.5 flavour, floored
        # at 0 so ultra-common terms contribute nothing rather than negative).
        df: dict[str, int] = {}
        for doc in self._docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        n = len(self._docs)
        self._idf = {
            term: max(0.0, math.log((n - f + 0.5) / (f + 0.5) + 1.0))
            for term, f in df.items()
        }
        self._tf: list[dict[str, int]] = []
        for doc in self._docs:
            counts: dict[str, int] = {}
            for term in doc:
                counts[term] = counts.get(term, 0) + 1
            self._tf.append(counts)

    def scores(self, query: str) -> list[float]:
        """BM25 score of `query` against every corpus document, in order."""
        terms = tokenize(query)
        out: list[float] = []
        for i in range(len(self._docs)):
            score = 0.0
            for term in terms:
                tf = self._tf[i].get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf.get(term, 0.0)
                denom = tf + self._k1 * (
                    1 - self._b + self._b * self._doc_len[i] / (self._avg_len or 1.0)
                )
                score += idf * tf * (self._k1 + 1) / denom
            out.append(score)
        return out


def squash(score: float, *, half: float = 5.0) -> float:
    """BM25 scores are unbounded and query-dependent; squash to (0, 1) so a
    relevance floor can be configured in stable units (score `half` -> 0.5).

    half=5.0 is sized to workspace-scale corpora (tens of chunks): one rare
    term (idf ≈ 3) lands ~0.37, clearing the 0.30 floor; common-word overlap
    (idf ≤ 1) stays well under it. Verified by evals/retrieval.py's report.
    """
    return score / (score + half) if score > 0 else 0.0


def rrf_fuse(rankings: list[list[int]], *, k: int = 60) -> dict[int, float]:
    """Reciprocal-rank fusion: item -> sum of 1/(k + rank+1) across rankings.

    The standard trick for combining rankings whose raw scores live on
    incomparable scales (cosine vs BM25): only *positions* matter, and k=60
    dampens the head so one list can't dominate alone.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank + 1)
    return fused
