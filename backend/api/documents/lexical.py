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
    """Okapi BM25 over a fixed corpus, built once and queried many times.

    Postings, not a per-document scan. A query's terms appear in a handful of
    chunks, so scoring only has to visit those: the cost tracks the number of
    *matching* documents rather than the size of the corpus. Scanning every
    document instead was the last linear-in-corpus step in a grounded send, and
    at 50,000 chunks it was most of the wait.

    The index is held by `DocumentIndex` for as long as the corpus is unchanged
    (see `_WorkspaceIndex`); it used to be rebuilt on every single query, which
    re-tokenised the whole workspace to answer one question.
    """

    def __init__(self, corpus: list[str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._n = len(corpus)
        self._doc_len: list[int] = []
        # term -> [(document index, term frequency), ...]
        self._postings: dict[str, list[tuple[int, int]]] = {}
        for i, text in enumerate(corpus):
            counts: dict[str, int] = {}
            length = 0
            for term in tokenize(text):
                counts[term] = counts.get(term, 0) + 1
                length += 1
            self._doc_len.append(length)
            for term, tf in counts.items():
                self._postings.setdefault(term, []).append((i, tf))
        self._avg_len = (sum(self._doc_len) / self._n) if self._n else 0.0
        # Document frequency per term -> smoothed idf (the +0.5 flavour, floored
        # at 0 so ultra-common terms contribute nothing rather than negative).
        self._idf = {
            term: max(0.0, math.log((self._n - len(posts) + 0.5) / (len(posts) + 0.5) + 1.0))
            for term, posts in self._postings.items()
        }

    def scores(self, query: str) -> list[float]:
        """BM25 score of `query` against every corpus document, in order.

        Still returns a dense list, because the caller fuses it positionally
        with the dense arm — but only the documents that actually contain a
        query term are ever touched.
        """
        out = [0.0] * self._n
        avg = self._avg_len or 1.0
        for term in tokenize(query):
            posts = self._postings.get(term)
            if not posts:
                continue
            idf = self._idf.get(term, 0.0)
            if idf <= 0.0:
                continue
            for i, tf in posts:
                denom = tf + self._k1 * (1 - self._b + self._b * self._doc_len[i] / avg)
                out[i] += idf * tf * (self._k1 + 1) / denom
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
