"""Pluggable LLM provider layer.

The product is model-agnostic: every part of Helix talks to an LLM only through
the `LLMProvider` interface, so swapping Groq <-> Ollama <-> stub is a config
change, never a code change. (helix-build-plan.md, decision #3.)
"""
from .base import LLMProvider, get_provider

__all__ = ["LLMProvider", "get_provider"]
