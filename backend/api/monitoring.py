"""Crash reporting (P4) — Sentry when configured, nothing at all when not.

The same posture as `telemetry.py`: opt-in and env-gated. With `SENTRY_DSN`
unset there is no SDK, no network client, and no behaviour change, so the
hermetic test suite and the zero-infra self-host story are untouched. A
self-hoster should never have their errors shipped to somebody else's account
by default — and on a hosted instance, finding out about a 500 from a user is
worse than finding out from an alert.

The dependency is optional. `sentry-sdk` is not in requirements.txt, because
requiring a monitoring SaaS client to run a self-hosted app is backwards; if it
is absent, this degrades to the same no-op as an unset DSN. Install it where you
actually want reporting:

    pip install sentry-sdk

What is deliberately *not* sent: `send_default_pii` stays off, so request
bodies, headers, and cookies do not leave the process. Helix carries workspace
provider API keys and message content — a crash report is not worth exfiltrating
either.
"""
from __future__ import annotations

import logging

from .config import settings

log = logging.getLogger(__name__)


def init_monitoring() -> bool:
    """Wire up crash reporting. Returns whether it actually engaged.

    Never raises: monitoring that prevents the app from booting has inverted its
    own purpose.
    """
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        # Configured but unavailable is worth saying out loud — the operator
        # asked for reporting and is not getting it.
        log.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; "
            "crash reporting is off. Install it with: pip install sentry-sdk"
        )
        return False

    try:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            # Errors always; traces only if explicitly asked for. Performance
            # tracing on a free tier burns the quota that error reporting needs.
            traces_sample_rate=settings.sentry_traces_sample_rate,
            # Off, emphatically: see the module docstring. Request bodies here
            # contain message content, and headers contain bearer tokens.
            send_default_pii=False,
        )
    except Exception:
        log.exception("Sentry init failed; continuing without crash reporting")
        return False

    log.info("Crash reporting enabled (environment=%s)", settings.sentry_environment)
    return True
