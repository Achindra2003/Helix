# Helix — Open-Source Release Plan

How to take Helix from "runs on localhost for a panel" to a public
open-source project people self-host, plus a free hosted instance where
anyone can sign up and plug in **their own** Groq key (or point a self-hosted
copy at Ollama). Companion to `MARKET-VALIDATION.md` (the landscape) and
`REQUIREMENTS-COVERAGE.md` (what's built). Written July 2026 against the
`ui-standout` branch, which is the release codebase.

**The model:** no billing, no plans, no seat pricing. Two tracks:

- **Track A — the repo.** The product *is* the open-source project. Success
  is measured in stars, self-host installs, and contributors.
- **Track B — the hosted demo.** A free public instance (helix.example.com)
  that markets the repo. Users bring their own LLM key, so the operating
  cost is a small VM, not a token bill.

**Why BYO-key changes everything:** the commercial plan's existential risk —
strangers spending your tokens — mostly evaporates. Each workspace burns its
*own* Groq key. What remains is ordinary web-service hygiene (auth, rate
limits on signup, data safety), which is a much shorter list.

**One constraint to be honest about everywhere:** a hosted website cannot
reach a user's local Ollama (`localhost:11434` is *their* machine). So:
**Ollama is the self-host story; BYO Groq key is the hosted story.** The
hosted UI should say exactly that.

---

## Phase 1 — The one real feature: per-workspace provider settings

Everything else in this plan is packaging; this is code. Today the provider
(`llm_provider`), the Groq key, and both model names are **server-wide
`.env` settings** (`api/config.py`), and Deep Reasoning builds its own
`ChatGroq` client from that same global config. Fine for self-host (one team,
one server, one key) — impossible for a multi-tenant hosted site.

Build:

1. **A `workspace_settings` row** (or columns on workspace): `provider`
   (`groq` | `openai_compatible`), `api_key` (encrypted), `base_url` (for
   OpenAI-compatible endpoints — this is how a hosted user could still point
   at a *publicly reachable* Ollama/vLLM if they really want), `chat_model`,
   `deep_model`. Server-wide env values remain the **fallback** — so
   self-hosters configure nothing new and the hosted instance simply ships
   with no fallback key.
2. **Encrypt keys at rest** (Fernet, keyed off the server secret). Never
   return the key in any API response — write-only field, display as
   `gsk_…last4`. Owner-only (RBAC already distinguishes owner).
3. **Thread it through the two call sites:** `get_provider()` for chat and
   `build_ouroboros_graph(...)` for deep runs both take the workspace's
   resolved settings instead of reading module-level config. The `LLMProvider`
   seam and the graph's explicit-client design (it already refuses to read
   ambient env) make this a plumbing change, not a redesign.
4. **Settings UI:** a "Provider" panel in the workspace (owner-only) — pick
   provider, paste key, pick models, **"Test connection"** button (one cheap
   completion round-trip with a clear error). Plus the empty-state nudge:
   a workspace with no key and no server fallback shows "plug in a key to
   start" instead of a dead composer.
5. **A "no key" grace path for the hosted demo:** browsing, the Map, replay,
   and exports all work keyless — only new turns need a key. A seeded example
   workspace (see 3.2) therefore demos almost the whole product before the
   user pastes anything.

Estimated effort: the bulk of one week. It also *improves* the self-host
story (per-team models on a shared family/lab server).

---

## Phase 2 — Track A: the repository as a product

### 2.1 Make `docker compose up` the whole install
- **Fix the Dockerfile** (currently dev-mode): drop `--reload`, non-root
  user, healthcheck. Add a stage that builds the frontend and lets FastAPI
  serve the static bundle — so the minimal install is **one container +
  one volume** (SQLite is a *feature* for self-hosters, not a liability).
- `docker-compose.yml` (simple: app + volume) and
  `docker-compose.postgres.yml` (app + Postgres) — the config already
  accepts a Postgres URL and `asyncpg` already ships.
- Publish images to **GHCR** on tagged releases via GitHub Actions; CI badge
  runs the 69-test hermetic suite (stub provider — no key needed in CI, which
  is already true and worth bragging about in the README).
- `.env.example` with every setting commented, including the Ollama recipe
  (`llm_provider=ollama`, compose file with an optional `ollama` service).

### 2.2 Hygiene that makes strangers trust a repo
- **License:** MIT (or Apache-2.0 if patent language feels warranted —
  decide once, day one; everything else blocks on it).
- **README rewrite for two audiences in order:** (1) a 90-second pitch with
  a demo **GIF of the two-browser moment** (teammate's tokens streaming into
  your thread, then steering their deep run — that clip is the marketing),
  (2) the quickstart: `git clone && docker compose up`, register, paste a
  free Groq key or point at Ollama. Architecture/docs links below the fold.
- `CONTRIBUTING.md` (dev setup, test commands, "good first issue" areas:
  providers, empty states, docs), issue/PR templates, `SECURITY.md` with a
  disclosure contact.
- The docs already exist and are accurate (`AI-ARCHITECTURE.md`, coverage,
  market validation) — link them; don't rewrite them.
- **Secure-by-default sweep:** refuse to start with
  `jwt_secret == "dev-only-change-me"` unless `HELIX_DEV=1`; generate and
  print a random secret on first run instead. Self-hosters will never read
  the warning; make the default safe.
- Tag **v1.0.0**. Cut releases with human-written notes.

### 2.3 What self-host explicitly supports (write it down)
- SQLite single-container (default) or Postgres compose.
- Groq, Ollama, or any OpenAI-compatible endpoint per workspace (Phase 1).
- **Single API process** — the WebSocket rooms (`api/realtime.py`) are
  in-memory, so document "scale vertically; one instance." For a self-hosted
  team of 5–50 this is genuinely fine. Redis pub/sub fan-out is a documented
  future path (the `roster()`/broadcast seam is narrow), and a labeled
  good-first-issue — classic OSS contribution bait.

---

## Phase 3 — Track B: the free hosted instance

A live demo with persistence, not a production SaaS. Set expectations in a
banner and a data policy, then run it cheaply and honestly.

### 3.1 Hardening subset (what actually remains without billing/LLM risk)
- **Postgres + Alembic + nightly `pg_dump`** on the hosted instance only.
  (Self-hosters keep boot-time `create_all` + SQLite; migrations ship in the
  repo for both.)
- **Rate limits** on signup and message routes (per-IP/per-user) — the
  threat is now DB spam and WS connection floods, not token theft. Modest
  caps: workspaces per user, members per workspace, message length.
- **Password reset** via a transactional email free tier (Resend). Skip
  email *verification* at launch — BYO-key means a fake account can't spend
  anything; reset is the one email flow people genuinely need.
- Invite codes get expiry + max-uses.
- **XSS audit** of rendered markdown (react-markdown defaults are safe —
  verify nothing re-enables raw HTML) — this matters more now that strangers
  share workspaces.
- Sentry free tier + UptimeRobot on `/health`.

### 3.2 The 30-second first run
- **Seeded example workspace** for every new user — pre-forked thread, a
  reference edge, a finished deep-run trace — so the Map, the monitor, and
  replay all demo *keyless* before they paste a key.
- Getting-started checklist: paste key → send → fork → open the Map → invite
  someone. The activation event is **the second user arriving** — make the
  invite email/link one click.
- A visible "this is a free demo instance — data may be wiped with notice;
  self-host for keeps → GitHub" banner. It sets expectations *and* funnels
  to the repo, which is the actual product.

### 3.3 Where it runs
- One VM/container host (Fly.io / Railway / Hetzner+Caddy): app + Postgres +
  Caddy for TLS. **~$5–15/month** — the entire operating cost of the product.
- CORS/base-URL/secret via env (all already env-driven), staging = the same
  compose file with throwaway data.

---

## Phase 4 — Release motion

1. **Soft launch (week 3–4):** repo public, v1.0.0 tagged, hosted instance
   live. 5–10 real teams (classmates, labmates, one Discord) kick the tires.
   Watch for onboarding confusion, not engine bugs (69 hermetic tests + live
   drives behind it).
2. **Public posts, each with its native hook:**
   - **Show HN:** "open-source collaborative AI workspace — branch, watch
     teammates think, steer runs mid-flight."
   - **r/selfhosted:** one-container install, SQLite default, your keys,
     your data.
   - **r/LocalLLaMA:** the Ollama story — a *multiplayer* UI for local
     models, which basically doesn't exist.
   - PR to **awesome-selfhosted** / awesome-ollama lists (steady drip of
     installs long after launch day).
3. **The demo GIF is the whole campaign.** Two browsers: tokens streaming in
   with the attribution banner, the Map's presence dot moving, a steer
   pivoting a deep run. 60 seconds, no narration needed.
4. **Post-launch:** triage for two weeks, label good-first-issues (Redis
   fan-out, new providers, file grounding), respond fast — early
   responsiveness is what turns stars into contributors. Roadmap stays the
   validation doc's gap list: file/knowledge grounding → model picker per
   chat → (only if hosted demand appears) multi-instance realtime.

---

## Sequencing (solo builder, honest sizing)

| Week | Work |
|------|------|
| 1 | Per-workspace provider settings (backend + encryption + tests) + settings UI + test-connection |
| 2 | Dockerfile/compose/GHCR + secure-by-default secret + license/README/CONTRIBUTING + demo GIF |
| 3 | Hosted instance: Postgres/Alembic/backups, rate limits, password reset, seeded workspace, banner; soft launch |
| 4 | Beta fixes, XSS/small-screen pass, launch posts |

**The four decisions that matter most:**
1. **BYO-key per workspace is the product change** — everything else is
   packaging. Build it first; both tracks depend on it.
2. **Ollama = self-host, Groq key = hosted.** Say it plainly in the UI and
   README instead of letting users discover the localhost problem.
3. **SQLite + one container is the self-host default, on purpose.** Zero-infra
   install is a feature; Postgres is the hosted instance's problem.
4. **The repo is the product; the hosted site is its demo.** Every hosted-side
   corner cut (data-wipe banner, no email verification, one instance) is fine
   *because* the durable path is self-hosting.
