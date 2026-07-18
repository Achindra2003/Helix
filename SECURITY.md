# Security Policy

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security vulnerabilities.

Preferred: use [GitHub's private vulnerability reporting](../../security/advisories/new)
for this repository (Security tab → "Report a vulnerability"). If that's not
available, email **pokemonzeee@gmail.com** with a description of the issue,
steps to reproduce, and its potential impact.

We'll acknowledge reports within a few days and keep you updated as a fix is
developed. Please give us a reasonable window to ship a fix before any
public disclosure.

## Supported versions

Helix is pre-1.0; security fixes land on the active development branch
(currently `ui-standout`) rather than being backported to older tags.

## Known posture (read before reporting the obvious)

Helix is honest about where it currently stands, so a few things are
already tracked rather than surprises:

- **Self-hosted deployments** are the primary security boundary today:
  server-side RBAC and tenancy are enforced on every route (see
  `REQUIREMENTS-COVERAGE.md` NFR-5), but the production hardening sweep
  (secure-by-default secret refusal, rate limiting, Postgres row-level
  security) is in progress — check `BATON-MANSOOR.md` and `LAUNCH-PLAN.md`
  for current status before assuming a hosted instance is hardened.
- **BYO-key model:** each workspace supplies its own LLM API key
  (encrypted at rest); a compromised account can spend that workspace's own
  key, not a shared operator key.
- **Untrusted content boundaries:** cross-conversation references, semantic
  recall, and file-grounding citations are all treated as quoted data, not
  instructions, to the model — see the injection-regression suite at
  `backend/api/conversation/tests/test_injection_regressions.py` for the
  attack corpus we actively test against.

If you find a gap in any of the above — or something not listed here —
that's exactly what this policy is for.
