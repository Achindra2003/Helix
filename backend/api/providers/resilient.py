"""Resilient provider wrapper: retry, circuit-breaker, and fallback at the LLM seam.

The chat seam used to make one bare call: a transient 429/5xx surfaced as a torn
or empty stream, and a dead key was retried on every single request. This wraps
any ordered list of providers [primary, *fallbacks] with three behaviours:

- **retry** transient failures that happen *before the first token* (a blip, not
  a reasoning signal) with exponential backoff;
- a per-endpoint **circuit breaker** so a sustained failure trips fast instead of
  hammering a known-dead provider on every request;
- **fall back** to the next provider when the primary fails before streaming —
  but never mid-stream, where a switch would duplicate already-emitted text.

Deep runs already retry internally (`_ainvoke_with_retry` in the Ouroboros
nodes); this brings the same honesty to plain chat. Soft rate-limits that a
provider chooses to surface as a visible notice (Groq's 429 path) are left
untouched — this layer only acts on raised exceptions.
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

from .base import Message

# Transient markers, matched against the exception's type name + message so this
# spans the Groq/OpenAI/httpx exception families without importing any of them.
# Kept local so the API layer never imports the vendored engine's copy.
_TRANSIENT_MARKERS = (
    "ratelimit", "rate limit", "rate_limit", "429",
    "500", "502", "503", "504",
    "timeout", "timed out", "connection", "overloaded", "temporarily",
)


def is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


class CircuitBreaker:
    """Trips open after `threshold` consecutive failures, then half-opens after
    `cooldown` seconds to allow a single trial. Any success closes it again."""

    def __init__(self, *, threshold: int = 4, cooldown: float = 30.0) -> None:
        self._threshold = threshold
        self._cooldown = cooldown
        self._failures = 0
        self._opened_at = 0.0

    def allow(self) -> bool:
        """True if a call may proceed (closed, or half-open after cooldown)."""
        if self._failures < self._threshold:
            return True
        return (time.monotonic() - self._opened_at) >= self._cooldown

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()


# Process-global breaker registry, keyed by endpoint identity, so every request's
# freshly-constructed provider shares one breaker per real backend.
_BREAKERS: dict[str, CircuitBreaker] = {}


def _breaker_for(key: str, *, threshold: int, cooldown: float) -> CircuitBreaker:
    breaker = _BREAKERS.get(key)
    if breaker is None:
        breaker = CircuitBreaker(threshold=threshold, cooldown=cooldown)
        _BREAKERS[key] = breaker
    return breaker


def _provider_key(provider) -> str:
    """Stable identity for a backend: name + endpoint + model. Two requests
    hitting the same Groq key/model share a breaker; different endpoints don't."""
    endpoint = getattr(provider, "_url", "") or getattr(provider, "_base_url", "")
    model = getattr(provider, "_model", "")
    return f"{getattr(provider, 'name', 'provider')}|{endpoint}|{model}"


_TRUNCATION_NOTICE = "\n\n[The response was cut off by a provider error — please retry.]"


class ResilientProvider:
    """Wraps [primary, *fallbacks] with retry + circuit-breaker + fallback.

    A drop-in `LLMProvider`: exposes `stream` and `stream_messages`, and reports
    the primary's `name`.
    """

    def __init__(
        self,
        providers,
        *,
        attempts: int = 3,
        base_delay: float = 1.0,
        breaker_threshold: int = 4,
        breaker_cooldown: float = 30.0,
    ) -> None:
        self._providers = [p for p in providers if p is not None]
        if not self._providers:
            raise ValueError("ResilientProvider needs at least one provider")
        self.name = self._providers[0].name
        self._attempts = max(1, attempts)
        self._base_delay = base_delay
        self._bt = breaker_threshold
        self._bc = breaker_cooldown
        # Accounting passthrough: usage/model of whichever inner provider
        # actually served the last stream (the primary, unless it fell back).
        self.last_usage: dict | None = None
        self._model = getattr(self._providers[0], "_model", "")

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async for chunk in self._run("stream", prompt):
            yield chunk

    async def stream_messages(self, messages: list[Message]) -> AsyncIterator[str]:
        async for chunk in self._run("stream_messages", messages):
            yield chunk

    async def _run(self, method: str, arg) -> AsyncIterator[str]:
        errors: list[str] = []
        self.last_usage = None
        for provider in self._providers:
            breaker = _breaker_for(
                _provider_key(provider), threshold=self._bt, cooldown=self._bc
            )
            if not breaker.allow():
                errors.append(f"{provider.name}: circuit open")
                continue
            for attempt in range(self._attempts):
                produced = False
                try:
                    async for chunk in getattr(provider, method)(arg):
                        produced = True
                        yield chunk
                    breaker.record_success()
                    self.last_usage = getattr(provider, "last_usage", None)
                    self._model = getattr(provider, "_model", self._model)
                    return
                except Exception as exc:
                    if produced:
                        # Committed mid-stream: retrying or falling back would
                        # duplicate the text already emitted. Stop cleanly.
                        breaker.record_failure()
                        yield _TRUNCATION_NOTICE
                        return
                    if is_transient(exc) and attempt < self._attempts - 1:
                        await asyncio.sleep(self._base_delay * (2 ** attempt))
                        continue  # retry the same provider
                    breaker.record_failure()
                    errors.append(f"{provider.name}: {type(exc).__name__}")
                    break  # give up on this provider, try the next
        yield (
            "[All configured providers are currently unavailable "
            f"({'; '.join(errors) or 'no providers'}). Please try again shortly.]"
        )
