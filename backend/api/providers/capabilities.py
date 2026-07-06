"""Model capability registry — code asks what a model supports, never assumes.

Providers and models churn; a capability the code hard-codes today (JSON mode, a
context length) breaks silently on the next swap. This answers three questions by
model-name pattern, with a conservative default for unknown models so a new model
degrades gracefully (features gated off) instead of crashing or producing garbage.

Match is by lowercase substring of the model name, most specific first. The point
is not a perfect spec sheet — it's a single place to look when a swap misbehaves,
and a seam callers can gate on (`if capabilities(model).json_mode: ...`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    context_tokens: int  # max context window the model accepts
    json_mode: bool  # supports response_format={"type": "json_object"}
    tools: bool  # supports tool / function calling


# Unknown models: assume a modest window and no structured/tool support, so
# callers gate those features on a real capability rather than an assumption.
_DEFAULT = ModelCapabilities(context_tokens=8_192, json_mode=False, tools=False)

# Pattern -> capabilities. First substring match wins; order specific before
# general. Numbers are the documented context windows as of the models in use.
_REGISTRY: tuple[tuple[str, ModelCapabilities], ...] = (
    ("llama-3.3-70b", ModelCapabilities(131_072, True, True)),
    ("llama-3.1-70b", ModelCapabilities(131_072, True, True)),
    ("llama-3.1-8b", ModelCapabilities(131_072, True, True)),
    ("llama-3.2", ModelCapabilities(131_072, True, True)),
    ("llama3.2", ModelCapabilities(131_072, False, False)),  # ollama tag
    ("llama-3", ModelCapabilities(8_192, True, True)),
    ("mixtral", ModelCapabilities(32_768, True, True)),
    ("gemma2", ModelCapabilities(8_192, True, False)),
    ("gemma", ModelCapabilities(8_192, False, False)),
    ("gpt-4o", ModelCapabilities(128_000, True, True)),
    ("gpt-4", ModelCapabilities(128_000, True, True)),
    ("gpt-3.5", ModelCapabilities(16_385, True, True)),
    ("qwen", ModelCapabilities(32_768, True, True)),
)


def capabilities(model: str | None) -> ModelCapabilities:
    """Best-known capabilities for a model name; the conservative default if unknown."""
    name = (model or "").lower()
    for pattern, caps in _REGISTRY:
        if pattern in name:
            return caps
    return _DEFAULT
