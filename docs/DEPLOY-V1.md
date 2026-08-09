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

**1. Memory.** The image bakes CPU PyTorch and MiniLM (`Dockerfile`, the
`sentence_transformers` warm-up). The recorded hosting plan is a free GCP
`e2-micro`: **1 GB of RAM, shared vCPU.** If the container's resident set does
not fit, the fix is architectural, not a flag — and it is much cheaper to learn
that from `docker stats` than from an OOM kill on a VM.

**2. Postgres.** The driver, the compose file and 20+ Alembic migrations exist
and have never been pointed at a real server. Four migration tests fail on
Windows for path reasons and are green on CI, so their *first* honest run
against Postgres is still ahead of us.

Everything in Stage A exists to retire these two before anything is provisioned.

---

## Stage A — on this machine, before any cloud

**A1. `docker compose up`, the default (SQLite).**
Register, make a workspace, send a message on the stub provider, upload a
document. This is the install a stranger will do, executed once by us first.
*Verify:* the app answers on :8000, the JWT secret is generated to `/data`, and
`docker compose down && up` keeps the account — a regenerated secret logs
everyone out and is the failure this volume exists to prevent.
*Measure:* `docker stats` at rest, and again during a grounded send (that is
when MiniLM is resident). **Write the number down.** It decides A4.

**A2. `docker compose -f docker-compose.postgres.yml up`.**
The parity run that has never happened.
*Verify:* point `frontend/app/e2e/rooms.mjs` at the container instead of its own
stack and run all three room journeys against Postgres. They pass on SQLite
today; anything that fails here is a genuine dialect difference — the class of
bug where SQLite accepts a foreign key Postgres rejects, which this repo has
been bitten by before.

**A3. Migrations against a real server.**
`alembic upgrade head` in the Postgres container, then `alembic check`.
*Verify:* no drift, and the four Windows-red migration tests pass inside the
container. That converts six known failures into two.

**A4. The embedder decision — with A1's number in hand.**
If the container fits comfortably in 1 GB, nothing to do. If it does not:

| Option | Cost | What it gives up |
|---|---|---|
| **e2-small instead** | ~$13/mo | Nothing. The plan's "free" claim. |
| **Drop `sentence-transformers`** | Free | Retrieval and convergence fall back to the lexical embedder. It works — the code path is deliberate and tested — but "semantic convergence" stops being semantic, and grounding quality drops on paraphrase. |
| **Hosted embeddings API** | Per-call | The offline, zero-infra self-host story. Fine for the hosted demo, wrong as the default. |

Recommendation: pay for `e2-small` before degrading the product. The neural
embedder is load-bearing for two of the three rooms.

---

## Stage B — the image

**B1.** Apply whatever A4 decided; rebuild; re-run A1's measurement.
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
