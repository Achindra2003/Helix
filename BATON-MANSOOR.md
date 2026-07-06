# Baton → Mansoor: the DB, infra & hardening lane of Helix

**Date:** July 6, 2026 · **Branch:** `ui-standout` (build here; `main` is the
frozen 25%-presentation version — never commit to it) · **Context:** the AI
lane is complete and contract-stable (177/177 tests, `351137c` → `2e870e4`);
Rajnish has the frontend baton (`BATON-RAJNISH.md`). Your lane is everything
that turns a working codebase into something strangers can run, trust, and
host: schema evolution, the production container, security hardening, and
the hosted instance.

Read in this order: this file → `AI-LANE-CONTRACTS.md` §3 (your formal
contract) → `LAUNCH-PLAN.md` (why each item exists; your work is its
Phases 2–3).

---

## 0. Orientation in one paragraph

Helix is a shared LLM workspace for teams (branchable conversations, live
multiplayer, steerable deep reasoning, BYO provider keys, file grounding).
The launch model is **open source, two tracks**: Track A — the repo *is* the
product (self-host: SQLite + one container, deliberately zero-infra);
Track B — a free hosted demo where each workspace brings its own LLM key,
so the operating cost is a small VM and the threat model is ordinary web
hygiene, not token theft. Your lane is what makes both tracks real.

## 1. Run it / test it

```bash
# backend (from backend/, venv exists at .venv)
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
./.venv/Scripts/python.exe -m pytest -q     # 177 tests, fully hermetic (stub provider, no keys)
```

The suite is your safety net: it runs with no network, no keys, no Docker.
Any change you make must keep it green, and anything you add (limits,
migrations, auth flows) needs tests in the same style (`api/conftest.py`
has the `make_user` / `make_workspace` / `join_workspace` factories).

## 2. What already exists in your lane (don't rebuild)

| Area | State |
|---|---|
| Auth | JWT (register/login), bcrypt, server-side identity on every route |
| Tenancy/RBAC | owner ⊃ collaborator ⊃ observer, enforced server-side everywhere; non-membership reads as 404 |
| Invites | token links with roles + **expiry** (`Invite.default_expiry`) — no max-uses yet |
| DB layer | SQLAlchemy async; SQLite dev / Postgres-ready (`asyncpg` ships, `database_url` config); `DbStore` behind a `ConversationStore` Protocol (store tests run against memory *and* DB) |
| Schema evolution | boot-time `create_all` + a forward-only **column shim** (`api/db.py::_add_missing_columns`) — deliberate stopgap, yours to replace for hosted |
| Docker | `backend/Dockerfile` + `docker-compose.yml` exist but are **dev-mode** (`--reload`, root user, no healthcheck, doesn't serve the frontend) |
| Realtime | in-process WS rooms (`api/realtime.py`) — single-instance by design; `roster()`/`broadcast()` is the narrow seam if Redis ever matters |

## 3. The work, in priority order

### P1 — The production container (`docker compose up` = the whole install)

Track A's product moment. From `LAUNCH-PLAN.md` §2.1:

- Multi-stage Dockerfile: build `frontend/app` (vite), serve the static
  bundle from FastAPI; drop `--reload`; non-root user; `HEALTHCHECK` on
  `/health`. Deep-reasoning deps (`requirements-engine.txt`) make the image
  heavy — consider a slim default image with deep reasoning as an optional
  build arg, and say which you chose in the README.
- `docker-compose.yml` (app + volume; SQLite is a *feature* for
  self-hosters) and `docker-compose.postgres.yml` (app + Postgres).
- GitHub Actions: run the hermetic suite on PRs (badge), publish the image
  to GHCR on tags.
- `.env.example` with every setting commented — the full list (including
  the new AI-lane settings) is in `AI-LANE-CONTRACTS.md` §3.3.

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
- **Rate limits** on signup and the message/deep routes (per-IP/per-user;
  slowapi or a small middleware — keep it dependency-light). The threat is
  DB spam and WS floods, not token theft (BYO keys burn the workspace's own
  key).
- Modest caps: workspaces per user, members per workspace, message length,
  **invite max-uses** (expiry already exists).
- Upload hygiene is already server-side (8 MB cap, extension allowlist,
  extracted-text cap) — verify, don't rebuild.

### P3 — Alembic baseline (schema evolution grows up)

Today: `create_all` for new tables + the column shim for new columns
(`api/db.py`). It works, it's tested (`test_db_shim.py`), and it's
deliberately minimal. Your job:

- Introduce Alembic with an initial autogenerated baseline of the current
  metadata (models live in `api/models.py`, `api/conversation/models.py`,
  `api/conversation/embeddings.py`, `api/documents/models.py`,
  `api/prompts/models.py`).
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
monitor, replay, and grounding all demo keyless); the data-wipe banner as a
config flag the frontend reads.

### P5 — Labeled seams from the AI lane (stretch, not blockers)

1. **Blob store for original files**: ingestion keeps extracted text only;
   re-upload = re-ingest. If file download matters, add storage behind the
   upload endpoint — nothing in the AI lane reads raw bytes after ingest.
2. **Restart-surviving deep runs**: run handles are in-process; the seam is
   LangGraph's sqlite checkpointer (`checkpointer=` param of
   `create_ouroboros_graph` already exists) + persisting the run registry +
   rebuild-on-boot. Genuinely hard; only worth it if hosted usage shows
   restarts eating runs. The durable `deep_runs` rows already keep the
   evidence trail.
3. **Redis pub/sub fan-out** for multi-instance realtime: documented,
   deferred, and still the right call to defer. Single instance is the
   stated posture for both tracks.

## 4. Ground rules

1. **Don't change AI-lane logic** (`api/providers/`, `api/conversation/`
   engine/producers/runs/embeddings, `api/documents/service.py`,
   `backend/engine/`). Schema/migration work *around* those models is
   yours; their behavior is contract-frozen — gaps go to Achindra.
2. The `ConversationStore` Protocol is the boundary you can lean on: the
   store test suite runs against both implementations and will catch you.
3. Response shapes are contracts with Rajnish's lane — coordinate before
   changing anything a route returns.
4. Commit per surface (P1, P2, …) to `ui-standout` with the suite green.
5. Never commit secrets; `.env` is gitignored — keep it that way.

## 5. References

- `AI-LANE-CONTRACTS.md` — §3 is your contract (tables, config, seams).
- `LAUNCH-PLAN.md` — the why and the week-by-week sizing (you own most of
  weeks 2–3).
- `REQUIREMENTS-COVERAGE.md` — what the SRS demands vs what's delivered.
- `HELIX-AI-EXPLAINED.md` — how the engine behind the routes thinks.

The repo is the product; your lane is what makes a stranger trust it enough
to run it. Ship the install.
