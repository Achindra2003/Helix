"""Transactional email (P4) — Resend when configured, a log line when not.

Only one flow needs email: password reset. Email *verification* is deliberately
skipped — BYO keys mean a fake account cannot spend anything, so verification
buys friction rather than safety, while reset is the flow people genuinely get
stuck without.

Unconfigured, `send` logs the message and reports failure instead of raising.
That keeps the self-hosted install free of an email dependency, keeps the test
suite hermetic, and — during local development — puts the reset link in the
server log where you can click it.

Resend is called over its HTTP API with httpx, which is already a dependency.
An SDK would add a package to send one POST.
"""
from __future__ import annotations

import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.resend.com/emails"


async def send(*, to: str, subject: str, text: str) -> bool:
    """Send one plain-text email. Returns whether it actually went out.

    Never raises. Callers treat email as best-effort: a password-reset request
    answers the same way whether or not delivery succeeded, because telling a
    stranger "no email was sent" tells them the address is not registered.
    """
    if not settings.resend_api_key:
        # Not an error — the ordinary self-hosted case. At debug level the body
        # is included so a developer can follow the reset link locally.
        log.info("Email not configured; would have sent %r to %s", subject, to)
        log.debug("Email body:\n%s", text)
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [to],
                    "subject": subject,
                    "text": text,
                },
            )
        if response.status_code >= 400:
            # The body carries Resend's reason (unverified domain, bad key).
            # Worth logging: silent non-delivery is the hardest failure to
            # diagnose, since the user-facing response is identical either way.
            log.error(
                "Resend rejected the email (%s): %s",
                response.status_code,
                response.text[:500],
            )
            return False
        return True
    except Exception:
        log.exception("Failed to send email to %s", to)
        return False
