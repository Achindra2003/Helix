"""Long-text embedding: stability must see the *whole* answer, not the first
256 tokens MiniLM would otherwise silently truncate to.
"""
from __future__ import annotations

import pytest

from ouroboros.memory import _word_chunks, cosine_similarity


def _neural_embedder_or_skip():
    """The real neural embedder, or skip — unlike `get_embedder()` (which falls
    back to the lexical embedder on any failure, by design), this test is
    specifically about the neural model's chunk-pooling behavior, so a network
    failure fetching model weights on a cold cache must skip, not fail."""
    pytest.importorskip("sentence_transformers")
    from ouroboros.memory import SentenceTransformerEmbedder

    try:
        return SentenceTransformerEmbedder()
    except Exception as exc:
        pytest.skip(f"sentence-transformers model unavailable (offline?): {exc}")


def test_short_text_is_a_single_chunk():
    assert _word_chunks("a short answer") == ["a short answer"]


def test_long_text_chunks_cover_every_word():
    words = [f"w{i}" for i in range(450)]
    chunks = _word_chunks(" ".join(words), chunk_words=180)
    assert len(chunks) == 3
    assert " ".join(chunks).split() == words  # nothing lost, nothing duplicated


def test_a_change_deep_in_a_long_answer_moves_the_similarity():
    """Two long answers identical for ~300 words, then diverging hard. Under
    truncation their similarity is ~1.0 (the difference is past the cutoff);
    with chunk-pooling it must be visibly below identical-pair similarity."""
    emb = _neural_embedder_or_skip()
    head = (
        "The migration should proceed in three phases with careful validation "
        "at each step, starting from the read paths and only then moving writes. "
    ) * 25  # ~300 words, well past the 256-token window
    tail_a = "Finally, the team should adopt Postgres and delete the legacy store."
    tail_b = (
        "However this entire plan is wrong: keep SQLite forever, the migration "
        "must be cancelled because the cost outweighs every benefit discussed."
    )
    vec_same_a, vec_same_a2, vec_b = emb.embed([head + tail_a, head + tail_a, head + tail_b])
    same = cosine_similarity(vec_same_a, vec_same_a2)
    diff = cosine_similarity(vec_same_a, vec_b)
    assert same > 0.999  # identical texts embed identically
    assert diff < same - 0.005  # the deep change is *visible* to the vector


def test_stability_on_long_drafts_is_governed_by_the_least_stable_region():
    """Whole-text pooling dilutes a localized change; chunk-wise stability must
    not. A long draft whose *ending* flips its recommendation is not stable —
    the controller should keep refining, not halt."""
    pytest.importorskip("sentence_transformers")
    from ouroboros.graph.controller import answer_stability

    head = (
        "The rollout has three phases: shadow reads, dual writes, and cutover. "
        "Each phase gates on an error budget and a rollback rehearsal. "
    ) * 20  # multi-chunk
    prev = head + "Conclusion: proceed with the migration next quarter."
    curr_same = head + "Conclusion: proceed with the migration next quarter."
    curr_flip = head + (
        "Conclusion: abandon the migration entirely; the risks make it "
        "indefensible and the team should invest elsewhere instead."
    )
    assert answer_stability(prev, curr_same) > 0.99
    assert answer_stability(prev, curr_flip) < 0.90  # below the halting threshold


def test_stability_flags_a_deleted_section():
    pytest.importorskip("sentence_transformers")
    from ouroboros.graph.controller import answer_stability

    body = (
        "Observability must ship with the feature: metrics, traces, and alerts. "
        "The oncall runbook needs the failure modes documented before launch. "
    ) * 20
    extra = (
        " Separately, the pricing model should move to usage-based billing with "
        "a grandfathering clause for existing annual contracts."
    ) * 4
    assert answer_stability(body + extra, body) < 0.90
