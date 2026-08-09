# Deploying Helix v1

The code is done. What follows is the order to find out whether it *runs*, and
the order matters more than the steps: everything here is arranged so the two
things that could still force a code change are discovered on a laptop, in
minutes, rather than on a VM at the end.

`docker compose up` has never been executed. Neither has Postgres. Both are
written, reviewed and covered by tests that use SQLite — which is precisely the
kind of confidence that evaporates on first contact.

---

## The two risks that decide everything else

**1. Memory — measured, 9 August.** The image bakes CPU PyTorch and MiniLM
(`Dockerfile`, the `sentence_transformers` warm-up). The recorded hosting plan
is a free GCP `e2-micro`: **1 GB of RAM, shared vCPU.**

Measured by staging the real imports in one process and reading the working set
(no Docker build needed — the risk is the Python process, and the wheels are
already installed locally):

| After loading | Resident |
|---|---|
| bare interpreter | 14 MB |
| \+ numpy | 27 MB |
| \+ the API (FastAPI, SQLAlchemy, routes) | 98 MB |
| \+ the Ouroboros engine (LangGraph/LangChain) | 313 MB |
| \+ MiniLM weights | 498 MB |
| \+ one embed call | 550 MB |
| \+ an ingest-sized batch (64 chunks) | **568 MB** |

So the app is roughly **570 MB steady-state once anything semantic has run**,
of which 470 MB is the engine and the embedder. Against 1 GB, minus ~150 MB for
a minimal Debian and the Docker daemon, that leaves on the order of 300 MB of
headroom. **It fits, and it is not comfortable.** Three consequences:

- **One uvicorn worker.** Each additional worker is another ~570 MB — the cap
  is memory, not CPU, and nothing in the plan needs a second one.
- **Do not build on the VM.** The build needs far more than the run; build
  elsewhere and pull the image (Stage B2 already says so).
- **Add swap anyway.** 2 GB of swap on the instance converts a spike from an
  OOM kill into a slow request.

Two caveats, stated rather than buried: this is a Windows working set, and
Linux RSS for the same stack is usually within a few tens of MB either way; and
it excludes the SQLite page cache and per-request allocations. It is the right
number to *plan* with and not a substitute for `docker stats` in A1 — but it is
now a confirmation step rather than a decision point.

**2. Postgres.** The driver, the compose file and 14 Alembic migrations exist
and have never been pointed at a real server. A static audit on 9 August
(below) found and fixed one defect that would have broken it; what remains is
the class of thing only a real server can show.

Everything in Stage A exists to retire these two before anything is provisioned.

---

## What the static Postgres audit found

Done without a server, on 9 August, because it is cheap and the alternative is
finding out during a deploy.

**Clean.** `GROUP BY` is strict-correct everywhere (every selected
non-aggregate column is grouped), so Postgres's stricter rule changes nothing.
Search filters in Python rather than SQL, so SQLite's case-insensitive `LIKE`
is not being relied on. JSON is stored as `Text` and booleans as `Boolean`, both
dialect-neutral. There is no raw SQL outside tests.

**One real defect, fixed.** `document_corpus_revisions.updated_at` was created
as `sa.DateTime()` — naive — while the model resolves to `TIMESTAMP WITH TIME
ZONE` through the declarative base. asyncpg refuses an aware value into a naive
column, so **every document upload and delete would have failed on Postgres**,
on any instance whose schema came from Alembic rather than `create_all`.

This is the same defect `e7b3c95a1d84` was written to repair in thirteen
columns on 6 August, reintroduced one table later on 9 August. It recurred
because nothing could see it: SQLite renders both spellings as `TIMESTAMP`, so
the drift guard — which runs `compare_type` against SQLite — compares them
equal. Two checks now catch it without a Postgres server
(`api/tests/test_migrations.py`): every timestamp column in the metadata must
be tz-aware, and no migration *after* the repair may spell one naively.

**A related fix.** Those migration tests derived the backend directory by
splitting `__file__` on `"/api/"`, which never matches on Windows — so all four
failed locally with a nonsense path, and the drift guard never ran outside CI.
That is four of the six "known Windows reds" gone, and it means the guard now
runs on the machine where the code is written.

**Still only provable on a real server:** connection/pool behaviour under
asyncpg, the `DB_NO_POOL` path the conftest takes for Postgres, and anything
about concurrent writers.

---

## Stage A — on this machine, before any cloud

**A1. `docker compose up`, the default (SQLite).**
Register, make a workspace, send a message on the stub provider, upload a
document. This is the install a stranger will do, executed once by us first.
*Verify:* the app answers on :8000, the JWT secret is generated to `/data`, and
`docker compose down && up` keeps the account — a regenerated secret logs
everyone out and is the failure this volume exists to prevent.
*Also verify:* pause a guided deep run, `docker compose down && up`, and steer
it. Checkpoints were landing in `/app` — the image layer — on any non-SQLite
database, so a paused run did not survive replacing the container. The image
now sets `CHECKPOINT_PATH=/data/helix-checkpoints.db`; this is the step that
proves it, and it is the same walk-away-and-come-back the feature exists for.
*Measure:* `docker stats` at rest, and again during a grounded send (that is
when MiniLM is resident). Expect ~570 MB for the app process, per the table
above; this run confirms the estimate on Linux rather than deciding anything.

**A2. `docker compose -f docker-compose.postgres.yml up`.**
The parity run that has never happened.
*Verify:* point `frontend/app/e2e/rooms.mjs` at the container instead of its own
stack and run all three room journeys against Postgres. They pass on SQLite
today; anything that fails here is a genuine dialect difference — the class of
bug where SQLite accepts a foreign key Postgres rejects, which this repo has
been bitten by before.

**A3. Migrations against a real server.**
`alembic upgrade head` in the Postgres container, then `alembic check`.
*Verify:* no drift, and specifically that a document upload and a delete both
succeed — that is the path the naive-timestamp defect broke, and the only way
to confirm the repair is a write against a real `TIMESTAMPTZ` column.
The four migration tests that used to fail on Windows are green now (the cause
was a path assumption, not the database), so two known local failures remain
and both are environmental: file modes, and a Tavily key in `.env`.

**A4. The embedder decision.**
Already decided by the measurement above: ~570 MB fits inside 1 GB with
roughly 300 MB of headroom, so **keep the neural embedder and stay on
`e2-micro`**, with one worker and 2 GB of swap. Revisit only if A1's
`docker stats` contradicts the estimate badly. The alternatives, if it does:

| Option | Cost | What it gives up |
|---|---|---|
| **e2-small instead** | ~$13/mo | Nothing. The plan's "free" claim. |
| **Drop `sentence-transformers`** | Free | Retrieval and convergence fall back to the lexical embedder. It works — the code path is deliberate and tested — but "semantic convergence" stops being semantic, and grounding quality drops on paraphrase. |
| **Hosted embeddings API** | Per-call | The offline, zero-infra self-host story. Fine for the hosted demo, wrong as the default. |

If it comes to a choice, pay for `e2-small` before degrading the product: the
neural embedder is load-bearing for two of the three rooms. On the measured
numbers it should not come to that.

**A5. Row-Level Security — *after* A2, never before.**
NFR-2 is 🟡: tenancy is enforced in the API on every route
(`_require_membership` / `_require_conversation`, 404 rather than 403 so probing
does not leak existence, with `api/tests/test_permission_matrix.py` behind it).
RLS is defence in depth against a route that *forgets* — its value scales with
how many people are adding routes.

Sequenced here rather than deferred, for a reason that is about debugging, not
effort: adding a policy layer before Postgres has ever run inverts the order of
questions. When a query returns zero rows on the first Postgres day, "app or
migration?" is answerable; "app, migration, or policy?" is much less so — and
the audit above already found one defect waiting in that first run.

*The trap that makes rushing it worse than skipping it:* Postgres table owners
bypass RLS by default. The app connects as the role that owns the schema, so
the likely outcome of a hasty pass is policies that exist, read correctly in the
migration, and are silently never enforced — a security control you now believe
in. Doing it honestly means a **separate non-owner application role**,
`FORCE ROW LEVEL SECURITY`, and a test that connects *as that role* — without
which the suite proves nothing.

*The decision A5 has to make first, from the schema as it stands (audited
9 August).* Fourteen tables carry `workspace_id` directly and take a one-line
policy: `conversations`, `documents`, `document_chunks`,
`document_corpus_revisions`, `deep_runs`, `resumable_runs`, `prompts`,
`llm_calls`, `notices`, `invites`, `memberships`, `workspace_settings`,
`mcp_servers`, `mcp_tools`.

Eight do not, and they are the problem:

| Table | Hops to `workspace_id` |
|---|---|
| `workspaces` | it *is* the root — predicate is "a workspace I am a member of" |
| `users` | not workspace-scoped at all; needs its own rule |
| `branches`, `conversation_references` | 1 (→ `conversations`) |
| `nodes`, `branch_votes` | 2 (→ `branches` → `conversations`) |
| `node_citations` | 3 (→ `nodes` → `branches` → `conversations`) |
| `node_embeddings` | 3, and it has **no declared foreign key** at all — only a bare `node_id` column |

`nodes` is the hottest table in the product — every message is a row — so a
policy that subqueries three levels up runs on every read of every thread. So
A5 opens with a choice, and it is a schema choice with a migration behind it:

1. **Denormalise `workspace_id`** onto `branches`, `nodes`, `branch_votes`,
   `node_citations`, `node_embeddings`, `conversation_references`. Every policy
   becomes identical and indexable; the cost is six columns to keep true, which
   is a backfill plus writes that already know the workspace.
2. **Join-based policies.** Nothing to backfill, and the predicate stays in one
   place — but the hot path pays for it, and `node_embeddings` needs its missing
   foreign key before it can even be expressed.

Recommendation: (1), and take the `node_embeddings` foreign key while there.
Uniform predicates are the ones that stay correct, and this is precisely the
work that is cheap now and expensive once there is data to backfill.

**Done, 9 August (`3f284ae`).** Option (1), migration `c8e41f7b3a26`: all six
tables carry `workspace_id`, NOT NULL, with the invariant checked against the
real routes; `node_embeddings.node_id` is a foreign key with ON DELETE CASCADE.
So A5 now starts at the policies, and every one of them is a one-liner.

What remains of A5 is the part that genuinely needs a server: the non-owner
application role, `FORCE ROW LEVEL SECURITY`, the policies themselves, and the
negative test that connects *as that role*. None of it should be attempted
before A2.

*Verify:* the permission matrix passes unchanged **as the non-owner role**, and
one hand-written negative test — connect as that role, `SELECT * FROM nodes`
with a foreign workspace's id set, and get zero rows. If that test can be made
to pass without the policies installed, it is not testing them.

---

## Stage B — the image

**B1.** Apply whatever A4 decided; rebuild; re-run A1's measurement. Set
`--workers 1` explicitly rather than relying on the default — the memory budget
is what caps it, and a future reader changing that number should have to read
this line first.
**B2.** Tag `v1.0.0`, push to GHCR.
*Verify:* `docker run ghcr.io/<owner>/helix:v1.0.0` on a clean machine with no
repo checkout brings up a working app. That is the claim the README makes.

---

## Stage C — the instance

**C1.** GCP VM (size per A4), Debian, Docker installed, firewall 80/443 only.
**C2.** Compose up, with `JWT_SECRET` set explicitly rather than generated —
one known secret is easier to rotate than one to go looking for.
**C3.** TLS. Caddy in front, one `Caddyfile`, automatic certificates. The app
serves the API and the built frontend on one port, so there is nothing to route
— this is a reverse proxy and not an ingress.
**C4.** Decide `ALLOW_REGISTRATION`. Open is right for a public demo and wrong
the moment it is a real instance; the knob and the invite-only path both exist.
**C5.** Seed the example workspace so the first screen is not empty.

---

## Stage D — operating it

**D1.** `pg_dump` on a cron to a bucket, and **restore it once** — a backup
nobody has restored is a belief, not a backup.
**D2.** UptimeRobot on `/health`.
**D3.** Sentry free tier.

Not doing yet, deliberately: Redis fan-out (single process is documented and
correct for this scale) and Postgres row-level security (tenancy is enforced on
every route today; RLS is defence in depth).

---

## Stage E — the release motion

**E1.** The GIF the launch plan calls "the marketing": two browsers, a
teammate's tokens streaming into your thread, then steering their deep run.
**E2.** Follow the README quickstart *literally*, on a clean machine, and fix
whatever it fails to say.
**E3.** Release notes, `v1.0.0`.

---

## The order, and what it protects

Stages A and B are reversible and cost a day. Everything after them is
provisioning, and provisioning is where an unmeasured assumption becomes an
outage. If time runs short, A1–A4 are the part that must not be skipped: they
are the difference between deploying and finding out.
