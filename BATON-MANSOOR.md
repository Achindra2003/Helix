# Baton → Mansoor: the DB, infra & hardening lane of Helix

**Date:** July 17, 2026 (supersedes the July 6 version) · **Branch:**
`ui-standout` (build here; `main` is the frozen 25%-presentation version —
never commit to it) · **Context:** the product lane is **finished** — all
16 functional requirements delivered, backend suite at **261 hermetic
tests**, frontend builds clean, and an automated browser click-through
(`frontend/app/e2e/smoke.mjs`) drives the whole golden path end-to-end.
Your lane is now the only thing between "finished product" and "something
strangers can run, trust, and host": the install, security hardening,
schema evolution, and the hosted instance. **Nothing in the plan below is
blocked on anyone else.**

Read in this order: this file → `AI-LANE-CONTRACTS.md` §3 (your formal
contract) → `LAUNCH-PLAN.md` (why each item exists; your work is its
Phases 2–3).

---

## 0. Before anything else: your clone is stale

Git history was **rewritten on July 16** (attribution trailers stripped
from every commit on all three branches) and force-pushed. Every commit
hash changed. On each branch you have checked out:

```bash
git fetch origin
git reset --hard origin/ui-standout   # (and likewise for main / v2-complete)
```

**Do not `git pull`** — a pull would merge the old history back in and
resurrect what was removed. If in doubt, re-clone.

## 1. Orientation in one paragraph

Helix is a shared LLM workspace for teams — branchable conversations, live
multiplayer, file grounding with cited RAG, proactive resurfacing ("a
teammate already explored this" while you type), a governed **Agent mode**
(owner-managed tool allowlist + human approval for sensitive calls), and a
steerable Deep Reasoning mode whose value claim is measured, not asserted
(`backend/evals/FINDINGS.md`, 8/8 hard-set coverage). The launch model is
**open source, two tracks**: Track A — the repo *is* the product
(self-host: SQLite + one container, deliberately zero-infra); Track B — a
free hosted demo where each workspace brings its own LLM key, so the
operating cost is a small VM and the threat model is ordinary web hygiene,
not token theft. Your lane is what makes both tracks real.

## 2. Run it / test it

```bash
# backend (from backend/, venv exists at .venv)
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
./.venv/Scripts/python.exe -m pytest -q     # 261 tests, fully hermetic (stub provider, no keys)

# frontend (from frontend/app/)
npm run dev                                  # Vite on :5173
npm run build                                # the typecheck gate

# full browser click-through (from frontend/app/; needs a GROQ key in
# backend/.env — it drives a real agent run and a real deep run)
node e2e/smoke.mjs                           # spawns its own backend+vite,
                                             # asserts 10 steps, screenshots
                                             # into docs/screenshots/
```

The hermetic suite is your safety net: no network, no keys, no Docker.
Any change you make must keep it green, and anything you add (limits,
migrations, auth flows) needs tests in the same style (`api/conftest.py`
has the `make_user` / `make_workspace` / `join_workspace` factories).
The e2e smoke is your second net: run it after anything that touches
serving, static files, or startup — it fails loudly if the golden path
breaks at the browser level.

## 3. What already exists (don't rebuild)

| Area | State |
|---|---|
| Auth | JWT (register/login), bcrypt, server-side identity on every route; change-password + delete-account flows exist |
| Tenancy/RBAC | owner ⊃ collaborator ⊃ observer, enforced server-side everywhere; non-membership reads as 404 |
| Invites | token links with roles + **expiry**, list/revoke — no max-uses yet |
| DB layer | SQLAlchemy async; SQLite dev / Postgres-ready (`asyncpg` ships, `database_url` config); `DbStore` behind a `ConversationStore` Protocol (store tests run against memory *and* DB). Env override is `DATABASE_URL` |
| Schema evolution | boot-time `create_all` + a forward-only **column shim** (`api/db.py::_add_missing_columns`) — deliberate stopgap, yours to replace for hosted |
| Docker | `backend/Dockerfile` + `docker-compose.yml` exist but are **dev-mode** (`--reload`, root user, no healthcheck, doesn't serve the frontend) |
| Realtime | in-process WS rooms (`api/realtime.py`) — single-instance by design; `roster()`/`broadcast()` is the narrow seam if Redis ever matters |
| Agent tools (FR-14, new since your last baton) | `api/tools/` package (its `__init__.py` docstring is the design doc): builtin catalog, owner allowlist on `WorkspaceSettings.tool_allowlist`, HITL approval for sensitive calls. Web search needs `tavily_api_key` in settings or it greys out — by design |
| Embeddings substrate | `NodeEmbeddingRow` (packed float32 in an ordinary column, on purpose) powers workspace search, resurfacing, and RAG recall |
| Usage/telemetry | `LlmCallRow` (`api/telemetry.py`) + a `/usage` endpoint per workspace |

## 4. The work, in priority order (unchanged in shape, updated in detail)

### P1 — The production container (`docker compose up` = the whole install)

Track A's product moment. From `LAUNCH-PLAN.md` §2.1:

- Multi-stage Dockerfile: build `frontend/app` (vite), serve the static
  bundle from FastAPI; drop `--reload`; non-root user; `HEALTHCHECK` on
  `/health`. Deep-reasoning deps (`requirements-engine.txt`) make the image
  heavy — consider a slim default image with deep reasoning as an optional
  build arg, and say which you chose in the README. (`frontend/app/e2e/`
  and Playwright are dev-only — exclude them from the image.)
- `docker-compose.yml` (app + volume; SQLite is a *feature* for
  self-hosters) and `docker-compose.postgres.yml` (app + Postgres).
- GitHub Actions: run the hermetic suite on PRs (badge), publish the image
  to GHCR on tags. The e2e smoke needs a key, so it stays out of CI.
- `.env.example` with every setting commented — the full list is in
  `AI-LANE-CONTRACTS.md` §3.3, **plus the FR-14 addition:**
  `TAVILY_API_KEY` (optional; enables the web_search tool's
  `available` flag).

Acceptance: a clean machine goes from `git clone` to registering a user at
`http://localhost:8000` with exactly one command; `pytest` runs in CI with
no secrets.

### P2 — Secure-by-default sweep

- **Refuse to boot with `jwt_secret == "dev-only-change-me"`** unless
  `HELIX_DEV=1`; generate and print a random secret on first run instead.
  (Self-hosters never read warnings; make the default safe.) Note: rotating
  the secret invalidates stored workspace provider keys by design
  (`provider_settings.py` derives its Fernet key from it) — the failure
  mode is "re-paste your key", never a leak; document it.
- **Rate limits** on signup and the message/deep/agent routes
  (per-IP/per-user; slowapi or a small middleware — keep it
  dependency-light). The threat is DB spam and WS floods, not token theft
  (BYO keys burn the workspace's own key). Agent runs count: each one can
  fan out multiple LLM + tool calls.
- Modest caps: workspaces per user, members per workspace, message length,
  **invite max-uses** (expiry already exists).
- Upload hygiene is already server-side (8 MB cap, extension allowlist,
  extracted-text cap) — verify, don't rebuild.

### P3 — Alembic baseline (schema evolution grows up)

Today: `create_all` for new tables + the column shim for new columns
(`api/db.py`). It works, it's tested (`test_db_shim.py`), and it's
deliberately minimal. Your job:

- Introduce Alembic with an initial autogenerated baseline of the current
  metadata. Models live in: `api/models.py` (note the newer
  `WorkspaceSettings` columns, incl. `tool_allowlist`),
  `api/conversation/models.py`, `api/conversation/embeddings.py`,
  `api/documents/models.py`, `api/prompts/models.py`, and
  `api/telemetry.py` (`LlmCallRow`) — **six files now, not five**.
- Posture per the launch plan: **self-hosters keep boot-time `create_all`**
  (zero-infra install); the **hosted instance runs migrations**. Keep the
  shim until the baseline lands, then it can retire behind a flag.
- Vectors are packed float32 in ordinary columns *on purpose* — no pgvector
  in the baseline. The escape hatch (only past ~10⁵ chunks/workspace) is
  two methods in `api/documents/service.py`; see `AI-LANE-CONTRACTS.md`
  §3.2.

### P4 — Hosted-instance kit (Track B)

From `LAUNCH-PLAN.md` §3: Postgres + nightly `pg_dump`; **password reset**
via a transactional-email free tier (Resend) — skip email *verification*,
reset is the one flow people need; Sentry free tier + UptimeRobot on
`/health`; a **seeded example workspace** per new user (pre-forked thread, a
reference edge, a finished deep-run trace, one uploaded doc — so the Map,
monitor, replay, grounding, and resurfacing all demo keyless); the
data-wipe banner as a config flag the frontend reads.

### P5 — Labeled seams from the AI lane (stretch, not blockers)

1. **Blob store for original files**: ingestion keeps extracted text only;
   re-upload = re-ingest. If file download matters, add storage behind the
   upload endpoint — nothing in the AI lane reads raw bytes after ingest.
2. **Restart-surviving runs**: run handles are in-process; the seam is
   LangGraph's sqlite checkpointer (`checkpointer=` param already exists
   on the graph builders) + persisting the run registry + rebuild-on-boot.
   **This now also covers agent runs paused for approval** — a sensitive
   tool call waiting on a human verdict dies with a restart (MemorySaver).
   Fine for the demo; it's the first bug report a real self-hoster will
   file, so it has moved up in value since July 6. The durable `deep_runs`
   rows already keep the evidence trail.
3. **Redis pub/sub fan-out** for multi-instance realtime: documented,
   deferred, and still the right call to defer. Single instance is the
   stated posture for both tracks.

## 5. Ground rules

1. **Don't change AI-lane or product logic** (`api/providers/`,
   `api/conversation/` engine/producers/runs/embeddings, `api/tools/`,
   `api/documents/service.py`, `backend/engine/`, and everything under
   `frontend/app/src/`). Schema/migration work *around* those models is
   yours; their behavior is contract-frozen — gaps go to Achindra.
2. The `ConversationStore` Protocol is the boundary you can lean on: the
   store test suite runs against both implementations and will catch you.
3. Response shapes are contracts with the frontend — that now includes the
   FR-14 routes (`GET/PUT /api/workspaces/{wid}/settings/tools`, the agent
   run/approve endpoints). Coordinate before changing anything a route
   returns.
4. Commit per surface (P1, P2, …) to `ui-standout` with the suite green.
   **No AI-attribution trailers in commit messages** (the July 16 rewrite
   exists precisely to keep the contributor graph human).
5. Never commit secrets; `.env` is gitignored — keep it that way.

## 6. References

- `AI-LANE-CONTRACTS.md` — §3 is your contract (tables, config, seams).
- `LAUNCH-PLAN.md` — the why and the week-by-week sizing (you own most of
  weeks 2–3).
- `REQUIREMENTS-COVERAGE.md` — 16/16 FRs delivered, mapped to the SRS.
- `README.md` — now the public face: identity, screenshots, measured
  claims. Your install instructions land here when P1 ships.
- `HELIX-AI-EXPLAINED.md` — how the engine behind the routes thinks.

The repo is the product; your lane is what makes a stranger trust it enough
to run it. Everything upstream of you is done and verified — ship the
install.
