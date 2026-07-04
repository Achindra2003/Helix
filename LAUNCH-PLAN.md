# Helix — Public Launch Plan

How to take Helix from "runs on localhost for a panel" to "strangers sign up
and use it." Companion to `MARKET-VALIDATION.md` (why the market wants this)
and `REQUIREMENTS-COVERAGE.md` (what's built). Written July 2026 against the
`ui-standout` branch, which is the launch codebase.

**The honest starting point:** the product is feature-complete for a v1 —
auth, multi-tenant workspaces with server-side RBAC, branchable shared
conversations, live multiplayer over WebSockets, the Map, steerable Deep
Reasoning with convergence halting, prompt library, exports. What it is *not*
yet is operable: it assumes one process, one SQLite file, one dev secret, a
free LLM tier, and a user who never forgets their password. Launch work is
therefore mostly **hardening and economics, not features**.

---

## Phase 0 — Decide the launch scope (a day of decisions, not code)

1. **Positioning:** "Git for your team's AI work" — small research groups,
   student teams, agencies (2–15 seats). Not enterprise; no SSO/SOC2 at v1.
2. **Plans:**
   - **Free** — 1 workspace, 3 members, chat on the fast 8B model,
     5 deep-reasoning runs/month, 7-day export retention of deleted data.
   - **Team ($15/seat/mo)** — unlimited workspaces/members, chat on 8B,
     deep reasoning on the 70B, fair-use token budget per workspace,
     priority runs. (Matches the $15–50/seat band from market validation.)
   - **Bring-your-own-key (free plan escape hatch)** — a workspace can attach
     its own Groq API key; their spend, our infra. This is the cheapest way
     to let the free tier be generous without eating the bill.
3. **Cut list for v1:** file/knowledge-base grounding, per-chat model picker,
   agent connectors, mobile apps. Named in-product as "coming"; they're
   roadmap, not launch blockers (validation doc agrees).

---

## Phase 1 — Production hardening (blocks any public user)

Ordered by blast radius. Everything here is prerequisite to exposing a port.

### 1.1 Data layer: SQLite → Postgres + real migrations
- The config already accepts `postgresql+asyncpg://…` and `asyncpg` is
  already in requirements — the seam exists. Stand up Postgres, run the suite
  against it (JSON columns, datetime, and `expire_on_commit` behaviors are
  the likely snags).
- Replace boot-time `create_all` with **Alembic** migrations. From the first
  public user onward the schema can never again be "whatever the models say."
- Automated daily backups (`pg_dump` to object storage) + a tested restore.
  A collaborative product's data *is* the product.

### 1.2 Secrets & auth hardening
- **Refuse to boot in prod with `jwt_secret == "dev-only-change-me"`.**
  One `if` in config; the single most important line in this plan.
- Email **verification** on signup and **password reset** — both need a
  transactional email provider (Resend or SES; ~zero cost at beta volume).
  Without reset, every forgotten password is a permanently lost account.
- Invite codes: add expiry + max-uses (currently they live forever).
- Shorten JWT TTL (7 days → 24h) + refresh tokens; add logout-everywhere by
  versioning a `token_generation` column on users.
- HTTPS everywhere (terminate at the proxy), `Secure`/`HttpOnly` if tokens
  move to cookies, standard security headers (CSP, HSTS) at the edge.

### 1.3 The realtime layer's one-process assumption
`_rooms` in `api/realtime.py` is a Python dict — presence and token fan-out
work only if every user of a workspace lands on the *same process*.
- **Beta decision: keep one API instance (scaled vertically) and document
  it.** A single decent VM handles hundreds of concurrent SSE/WS connections;
  this is not the bottleneck at launch scale.
- **The growth path, designed now, built later:** move room fan-out to
  **Redis pub/sub** (each instance subscribes to `workspace:{id}`; presence
  in Redis hashes with TTL heartbeats). The `roster()`/`_broadcast_presence()`
  seam is already narrow enough that this is a swap, not a rewrite.

### 1.4 Abuse control & LLM economics (the launch-killer risk)
Every signup can spend our tokens. Untreated, one Reddit hug = one dead Groq
key and a bill.
- **Rate limits** (Redis-backed, e.g. slowapi): per-IP on auth routes,
  per-user on message send, per-workspace concurrent deep runs (cap: 1 free /
  3 team). Max prompt length; max reference fan-in.
- **Metering:** per-workspace token ledger (the usage callback in the deep
  producer already counts tokens — persist it). Enforce plan budgets
  server-side; degrade gracefully ("budget reached — resumes on the 1st").
- **Provider:** move to Groq's paid tier (or add an OpenRouter fallback
  provider behind the existing `LLMProvider` seam) so a provider outage or
  tier limit isn't a product outage. Keep `stub` for CI forever.
- Email-verified accounts only may hit LLM routes; unverified can look around.

### 1.5 Deployment shape
- **Fix the Dockerfile**: drop `--reload`, run as non-root, multi-stage build,
  `--workers 1` explicitly (see 1.3), healthcheck.
- **docker-compose.prod.yml**: `api` + `postgres` + `redis` + `caddy`
  (auto-TLS reverse proxy, serves the built frontend statics, proxies
  `/api`, SSE and WS pass-through).
- **Host:** one provider that does containers + Postgres + volumes with
  WS/SSE support — Fly.io, Railway, or Render all fit; pick by price
  (~$20–40/mo all-in at beta). Frontend can also go to Cloudflare Pages with
  `VITE_API_BASE` pointed at the API host.
- CORS origin, `frontend_base_url`, and model names all already read from
  env — set them per environment; add a staging environment that is the
  prod compose file pointed at throwaway data.
- CI (GitHub Actions): backend suite (hermetic — already stub-provider) +
  frontend typecheck/build on every push; deploy on tag.

### 1.6 Observability — fly with instruments
- **Sentry** (backend + frontend) — first, cheapest, highest value.
- Structured JSON logs with request IDs; log every deep run's token count,
  duration, stop reason (this doubles as the billing ledger and the
  convergence-quality dataset).
- `/health` already exists — wire it to an uptime monitor (Better Stack /
  UptimeRobot) with alerting.
- A tiny ops dashboard can wait; the token-spend query cannot.

**Exit criteria for Phase 1:** staging URL where a stranger can register
(with email verify), get rate-limited when greedy, and where killing the API
container loses no data and recovers in under a minute.

---

## Phase 2 — Public-readiness product work

### 2.1 First-run experience (the demo without you narrating it)
The current empty workspace assumes a guided demo. Public users get 30
seconds. Ship:
- A **seeded example conversation** in every new workspace — pre-forked, with
  a reference edge and a finished deep-run trace, so the Map and monitor have
  something to show immediately.
- A 4-step first-run tour: send → fork → open the Map → run deep reasoning.
- **Invite-by-email** (send the link, not the code) — the product is
  multiplayer; the activation event is *the second user arriving*. Make that
  path one click.
- An empty-state on every view that says what the view is for (partly done
  in ui-standout; finish the sweep).

### 2.2 Trust & legal (boring, mandatory)
- Terms of Service + Privacy Policy (template-grade is fine at beta).
- **Account deletion** and **workspace data export** (per-thread export
  exists; add "export everything" — mostly the map aggregate + a zip).
- A plain-language data page: what's stored, that prompts go to Groq (US),
  what teammates can see (shared vs. private threads — the model is already
  good; write it down).
- Rendered-markdown XSS audit of the chat body (react-markdown defaults are
  safe — verify nothing re-enables raw HTML).

### 2.3 Billing
- **Stripe Checkout + customer portal** — subscriptions on the workspace,
  seat-counted, webhooks flip a `plan` column that the rate/budget middleware
  (1.4) already reads. No invoices, no proration cleverness at v1.
- Launch beta **free-only with a waitlisted Team plan** if Stripe work
  threatens the date — billing is the most deferrable item in this phase.

### 2.4 Small-screen sanity
Not mobile-first — but the marketing page, auth, and *reading* a thread must
not break on a phone, because the invite link will be opened on one.

---

## Phase 3 — Launch motion

1. **Week 0 — private beta:** 5–10 real teams (classmates' project groups,
   labmates, one Discord community). Success metric: a team that returns
   **without being asked**. Instrument three events: second-user-joined,
   first-fork, first-deep-run-steered.
2. **Iterate 2–3 weeks** on what the beta actually breaks (expect: onboarding
   confusion and rate-limit tuning, not engine bugs — the engine has 69
   hermetic tests and live drives behind it).
3. **Public launch:** Product Hunt + Hacker News (Show HN) + the r/LLMDevs
   corner. The demo asset is a 60-second screen recording of the two-browser
   moment: a teammate's tokens streaming into your thread, then steering
   their deep run mid-flight. That clip *is* the marketing.
4. **Post-launch roadmap = the validation doc's gap list, in order:**
   file/knowledge grounding → model picker → SSO when the first >15-seat
   team asks (that's the enterprise signal, not before).

---

## Sequencing & effort (solo builder, honest sizing)

| Weeks | Work |
|-------|------|
| 1–2 | Postgres + Alembic + backups; secrets/auth hardening; email verify + reset |
| 2–3 | Rate limits + token metering + paid Groq; prod Docker/compose/Caddy; deploy staging |
| 3–4 | Sentry + logging + uptime; seeded workspace + tour + invite-by-email |
| 4–5 | Legal pages + deletion/export; XSS audit; small-screen pass; private beta starts |
| 5–7 | Beta fixes; Stripe (or waitlist); launch assets |
| 8 | Public launch |

**The four decisions that matter most, restated:**
1. Refuse to boot with the dev JWT secret. (One line. Do it first.)
2. Postgres + migrations before the first stranger registers — data is the product.
3. Single API instance at launch, Redis fan-out designed but deferred — don't
   build distributed presence for zero users.
4. Token spend is the existential risk: verify emails, rate-limit, meter, cap
   deep runs, and offer BYO-key — *before* any link is public.
