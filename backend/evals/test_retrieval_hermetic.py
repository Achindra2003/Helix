"""Hermetic self-test for the retrieval eval harness.

Runs the full golden set through the real chunker/index with a deterministic
fake embedder (hashed bag-of-words — no model download, no network). Dense
numbers under this fake are not meaningful; the *lexical* arm is embedder-
independent, so its quality and the gate's zero-leakage promise are asserted
for real. The point: the harness itself must always run and report, so a
broken retrieval change can't hide behind "the eval needs a GPU".
"""
import asyncio

from evals.retrieval import ARMS, run_all


class HashedBowMem:
    """Deterministic 64-dim hashed bag-of-words embedder + cosine."""

    class _E:
        name = "test-hashed-bow"

        def embed(self, texts):
            out = []
            for t in texts:
                vec = [0.0] * 64
                for token in t.lower().split():
                    vec[hash(token) % 64] += 1.0
                norm = sum(x * x for x in vec) ** 0.5 or 1.0
                out.append([x / norm for x in vec])
            return out

    def get_embedder(self):
        return self._E()

    @staticmethod
    def cosine_similarity(a, b):
        return sum(x * y for x, y in zip(a, b))


def test_harness_runs_all_arms_and_lexical_quality_holds():
    reports, embedder = asyncio.run(run_all(memory=HashedBowMem()))
    assert embedder == "test-hashed-bow"
    assert [r.arm for r in reports] == list(ARMS)
    for r in reports:
        assert 0.0 <= r.recall_at_1 <= r.recall_at_k <= 1.0
        assert 0.0 <= r.mrr <= 1.0
        assert r.per_query  # every query judged

    lexical = next(r for r in reports if r.arm == "lexical")
    # BM25 doesn't depend on the embedder: real quality, asserted hermetically.
    assert lexical.recall_at_k >= 0.75
    assert lexical.negative_leakage == 0.0
