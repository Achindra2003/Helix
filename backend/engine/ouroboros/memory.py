"""Semantic memory: embedding-based retrieval over accumulated insights.

The default embedder is a local sentence-transformers model (``all-MiniLM-L6-v2``)
— free, offline after first download, no API keys. When that dependency or model
is unavailable (e.g. minimal install or CI), it transparently falls back to a
deterministic pure-python lexical embedder so the system always works; install
the real model with ``pip install -e '.[memory]'``.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_LEXICAL_DIM = 256


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class LexicalEmbedder:
    """Deterministic hashed bag-of-words embedding. No external dependencies.

    Cosine similarity over these vectors approximates weighted token overlap —
    a reasonable, fully-offline fallback when no neural model is available.
    """

    name = "lexical-fallback"

    def __init__(self, dim: int = _LEXICAL_DIM):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in _tokenize(text):
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            vectors.append(_l2_normalize(vec))
        return vectors


# MiniLM silently truncates input past its max sequence length (256 tokens,
# roughly ~190 words). Un-chunked, the "stability" of a long answer would
# measure only whether its *opening* stopped changing — a change buried deep in
# a two-page synthesis would be invisible to the convergence controller. Long
# texts are therefore split into word chunks, embedded separately, mean-pooled,
# and re-normalized, so every part of the text weighs on the vector.
_CHUNK_WORDS = 180


def _word_chunks(text: str, chunk_words: int = _CHUNK_WORDS) -> list[str]:
    """Split on whitespace into chunks of at most ``chunk_words`` words."""
    words = text.split()
    if len(words) <= chunk_words:
        return [text]
    return [
        " ".join(words[i : i + chunk_words]) for i in range(0, len(words), chunk_words)
    ]


class SentenceTransformerEmbedder:
    """Local neural embeddings via sentence-transformers (lazy-loaded).

    Long inputs are chunk-embedded and mean-pooled (see ``_word_chunks``) so
    similarity reflects the whole text, not the first 256 tokens.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.name = f"sentence-transformers/{model_name}"
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # One batched encode over every chunk of every text, then pool per text.
        all_chunks: list[str] = []
        spans: list[tuple[int, int]] = []
        for text in texts:
            chunks = _word_chunks(text)
            spans.append((len(all_chunks), len(chunks)))
            all_chunks.extend(chunks)
        embeddings = self._model.encode(all_chunks, normalize_embeddings=True)
        out: list[list[float]] = []
        for start, count in spans:
            if count == 1:
                out.append(list(map(float, embeddings[start])))
                continue
            rows = embeddings[start : start + count]
            mean = [float(sum(col)) / count for col in zip(*rows)]
            out.append(_l2_normalize(mean))
        return out


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Return the best available embedder, cached for the process.

    Prefers the local neural model; falls back to the lexical embedder if
    sentence-transformers is not installed or the model fails to load.
    """
    try:
        return SentenceTransformerEmbedder()
    except Exception:
        return LexicalEmbedder()


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def semantic_search(
    query: str,
    memories: list[str],
    k: int = 3,
    embedder: Embedder | None = None,
) -> list[tuple[str, float]]:
    """Return up to ``k`` (memory, score) pairs ranked by similarity to ``query``.

    Memory lists are small (capped by ``max_memories``), so embedding them on
    each call is cheap and avoids persisting vectors in graph state.
    """
    if not memories:
        return []
    emb = embedder or get_embedder()
    vectors = emb.embed([query, *memories])
    query_vec, mem_vecs = vectors[0], vectors[1:]
    scored = [
        (mem, cosine_similarity(query_vec, mem_vec))
        for mem, mem_vec in zip(memories, mem_vecs)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
