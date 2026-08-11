"""Request rate limiting (P2) — a sliding window, in process, no dependencies.

The threat is DB spam and run floods, not token theft: BYO keys mean a flood
burns the *workspace's* own provider quota, not the operator's. So the goal is
modest — stop one client from creating ten thousand accounts or queueing a
hundred deep runs — not to build a general-purpose traffic shaper.

Why not slowapi: the baton asks for dependency-light, and the whole mechanism
is the thirty lines below. A library would add a dependency, its own
middleware, and its own decorator vocabulary to buy the same thing.

Scale note, matching realtime.py: the counters are in-process dicts, correct
for the single API process this project deploys as. Multi-process would need a
shared store (Redis), and `_Window.hit` is the seam that would move.

Identity is the authenticated user when a valid token is present, else the
client IP. That ordering matters: keying only on IP would throttle a whole
office behind one NAT as though it were one person, and keying only on user
would leave signup — which has no user yet — unprotected.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

import jwt as pyjwt

from .config import settings
from .security import decode_token

# bucket name -> identity -> timestamps of recent hits (oldest first)
_hits: dict[str, dict[str, deque[float]]] = defaultdict(lambda: defaultdict(deque))

# Admitted events since each bucket was last swept (see _Window._sweep). Module
# state, not instance state: `limit_for` builds a fresh _Window per request, so
# anything stored on the instance is discarded before the next one arrives.
_since_sweep: dict[str, int] = defaultdict(int)

# How many admitted events between sweeps of idle identities (see _Window._sweep).
_SWEEP_EVERY = 256


class _Window:
    """One named limit: `limit` events per `window_s` seconds, per identity."""

    def __init__(self, name: str, limit: int, window_s: float) -> None:
        self.name = name
        self.limit = limit
        self.window_s = window_s

    def hit(self, identity: str, now: float | None = None) -> float | None:
        """Record an event. Returns None if allowed, else seconds to wait.

        Timestamps older than the window are discarded on every call, so a
        deque never outgrows `limit`. Whole identities are reclaimed separately,
        by `_sweep` — this method only ever sees identities that are sending.
        """
        if self.limit <= 0:
            return None  # 0 disables this limit
        now = time.monotonic() if now is None else now
        seen = _hits[self.name][identity]

        cutoff = now - self.window_s
        while seen and seen[0] <= cutoff:
            seen.popleft()

        if len(seen) >= self.limit:
            # Allowed again once the oldest hit falls out of the window.
            return max(0.0, seen[0] + self.window_s - now)

        seen.append(now)
        self._sweep(now)
        return None

    def _sweep(self, now: float) -> None:
        """Drop identities that have gone quiet, occasionally.

        Nothing else can: `hit` only ever runs for an identity that is sending
        right now, so an attacker who cycles through addresses and never
        returns would otherwise leave one dict entry per address forever. The
        sweep is O(identities) and runs once every `_SWEEP_EVERY` admitted
        events, which keeps it off the hot path while still bounding memory to
        roughly the number of identities actually active in a window.
        """
        _since_sweep[self.name] += 1
        if _since_sweep[self.name] < _SWEEP_EVERY:
            return
        _since_sweep[self.name] = 0
        cutoff = now - self.window_s
        bucket = _hits[self.name]
        for ident in [i for i, hits in bucket.items() if not hits or hits[-1] <= cutoff]:
            del bucket[ident]


def reset() -> None:
    """Drop all counters. For tests, and for nothing else."""
    _hits.clear()
    _since_sweep.clear()


def identity_for(request) -> str:
    """Who to charge this request to: user id if authenticated, else client IP.

    A malformed or expired token is not an error here — the route's own auth
    dependency will reject it properly. This only decides which bucket the
    attempt counts against, and an unauthenticated attempt counts against the
    IP, which is exactly right for a login-guessing flood.
    """
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        try:
            return f"user:{decode_token(header[7:].strip())}"
        except (pyjwt.PyJWTError, KeyError):
            pass
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def limit_for(method: str, path: str) -> _Window | None:
    """The limit that applies to a request, or None if unlimited.

    Read from `settings` on every call rather than captured at import, so tests
    (and an operator editing .env) can change a limit without reimporting.
    """
    if not settings.rate_limit_enabled or method.upper() not in {"POST", "PUT", "PATCH"}:
        return None

    # Account creation, login, and the reset flow: keyed by IP in practice,
    # since none of them carries a token. Guards mass-signup, password
    # guessing, and — for forgot-password — an open endpoint that makes the
    # server send email to an address of the caller's choosing, which is both a
    # billing problem and a way to have your sending domain reported as spam.
    if path in (
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
    ):
        return _Window("auth", settings.rate_limit_auth_per_hour, 3600.0)

    if path.startswith("/conversations"):
        # Deep and agent runs are the expensive ones: each can fan out into
        # many model and tool calls, so they get their own tighter budget.
        if path.endswith(("/deep", "/agent")):
            return _Window("runs", settings.rate_limit_runs_per_minute, 60.0)
        if "/messages" in path:
            return _Window("messages", settings.rate_limit_messages_per_minute, 60.0)

    # Uploads: the heaviest write in the app — up to document_max_bytes each,
    # plus a chunk row per ~220 words and an embedding per chunk. The extension
    # allowlist runs at ingest, *after* the document row is committed, so even
    # rejected files cost a row. Membership is required, so this is a limit on
    # authenticated members rather than the open internet, which is why it is
    # per-hour rather than per-minute.
    if path.startswith("/api/workspaces/") and path.endswith("/documents"):
        return _Window("uploads", settings.rate_limit_uploads_per_hour, 3600.0)

    return None
