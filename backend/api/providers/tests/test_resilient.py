"""Resilient provider: retry before first token, fallback, mid-stream honesty,
circuit breaker. Fakes are scripted per-call so retries and fallbacks are visible.
"""
import pytest

from api.providers import resilient
from api.providers.resilient import CircuitBreaker, ResilientProvider, is_transient


@pytest.fixture(autouse=True)
def _clear_breakers():
    """Breakers are process-global; isolate each test."""
    resilient._BREAKERS.clear()
    yield
    resilient._BREAKERS.clear()


class Scripted:
    """A provider whose behaviour on each call is a list of steps: a str is
    yielded, an Exception is raised at that point in the stream."""

    def __init__(self, name, calls):
        self.name = name
        self._calls = calls  # list-of-lists; one per invocation
        self.invocations = 0

    async def stream_messages(self, messages):
        idx = min(self.invocations, len(self._calls) - 1)
        self.invocations += 1
        for step in self._calls[idx]:
            if isinstance(step, Exception):
                raise step
            yield step

    async def stream(self, prompt):
        async for chunk in self.stream_messages([{"role": "user", "content": prompt}]):
            yield chunk


async def _collect(provider):
    return "".join([chunk async for chunk in provider.stream_messages([])])


# --- transient classification ---

def test_is_transient_matches_families():
    assert is_transient(RuntimeError("Rate limit reached (429)"))
    assert is_transient(Exception("upstream connection reset"))
    assert is_transient(Exception("503 Service Unavailable"))
    assert not is_transient(ValueError("invalid api key"))
    assert not is_transient(Exception("model not found"))


# --- retry before first token ---

@pytest.mark.asyncio
async def test_retries_transient_failure_before_first_token():
    # First call raises a transient error before yielding; retry succeeds.
    provider = Scripted("p", [[RuntimeError("rate limit 429")], ["hello ", "world"]])
    wrapped = ResilientProvider([provider], attempts=3, base_delay=0.0)
    assert await _collect(wrapped) == "hello world"
    assert provider.invocations == 2  # failed once, retried once


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts():
    provider = Scripted("p", [[RuntimeError("429 rate limit")]] * 5)
    wrapped = ResilientProvider([provider], attempts=3, base_delay=0.0)
    out = await _collect(wrapped)
    assert "unavailable" in out.lower()
    assert provider.invocations == 3  # exactly `attempts` tries


# --- fallback ---

@pytest.mark.asyncio
async def test_falls_back_to_next_provider_on_hard_failure():
    primary = Scripted("primary", [[ValueError("invalid api key")]])  # non-transient
    fallback = Scripted("fallback", [["from ", "fallback"]])
    wrapped = ResilientProvider([primary, fallback], attempts=3, base_delay=0.0)
    assert await _collect(wrapped) == "from fallback"
    assert primary.invocations == 1  # non-transient: not retried
    assert fallback.invocations == 1


@pytest.mark.asyncio
async def test_none_fallback_is_ignored():
    primary = Scripted("primary", [["ok"]])
    wrapped = ResilientProvider([primary, None], attempts=1, base_delay=0.0)
    assert await _collect(wrapped) == "ok"


# --- mid-stream failure cannot fall back ---

@pytest.mark.asyncio
async def test_midstream_failure_yields_truncation_not_fallback():
    primary = Scripted("primary", [["partial ", RuntimeError("connection dropped")]])
    fallback = Scripted("fallback", [["should not appear"]])
    wrapped = ResilientProvider([primary, fallback], attempts=3, base_delay=0.0)
    out = await _collect(wrapped)
    assert out.startswith("partial ")
    assert "cut off" in out.lower()
    assert "should not appear" not in out
    assert fallback.invocations == 0  # never reached


# --- circuit breaker ---

def test_breaker_opens_after_threshold_and_recovers_on_success():
    br = CircuitBreaker(threshold=2, cooldown=999.0)
    assert br.allow()
    br.record_failure()
    assert br.allow()  # 1 < 2
    br.record_failure()
    assert not br.allow()  # tripped, cooldown not elapsed
    br.record_success()
    assert br.allow()  # closed again


def test_breaker_half_opens_after_cooldown():
    br = CircuitBreaker(threshold=1, cooldown=0.0)
    br.record_failure()
    # cooldown of 0 means the half-open trial is immediately allowed
    assert br.allow()


@pytest.mark.asyncio
async def test_open_breaker_skips_provider_and_uses_fallback():
    dead = Scripted("dead", [[RuntimeError("429")]] * 10)
    fallback = Scripted("fallback", [["ok"]] * 10)
    # threshold=1 so the primary trips after its first failed request.
    wrapped = ResilientProvider(
        [dead, fallback], attempts=1, base_delay=0.0, breaker_threshold=1, breaker_cooldown=999.0
    )
    assert await _collect(wrapped) == "ok"
    dead_calls_first = dead.invocations
    # Second request: breaker for `dead` is open, so it is skipped entirely.
    assert await _collect(wrapped) == "ok"
    assert dead.invocations == dead_calls_first  # not called again
