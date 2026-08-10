# Deploy runbook — Helix v1 on a GCP instance

The executable half of `DEPLOY-V1.md`. That document argues about ordering and
risk; this one is a list of commands for someone who was not part of those
conversations. Where the two disagree, this file is what to run and that one is
why.

**Read the whole of "Before you start" before typing anything.** Two of the
steps below cannot be undone cheaply, and one of them is currently blocked.

---

## Who does what

| | |
|---|---|
| **Achindra** | GCP project + billing, DNS, and the go-ahead to publish the image (it creates a package under his GitHub account). `gcloud auth login` is interactive and has to be run by whoever owns the account. |
| **Mansoor** | Everything on the machine: instance, Docker, the stack, and the verification in step 9. |
| **Already done** | The image builds in CI, the full test suite passes against real Postgres, and the migrations have been applied to a real server. Nothing below should surface a code defect. If it does, stop and say so — that is a finding, not a step to work around. |

---

## Before you start

**Blocker — CI is red.** The `Backend tests (261, hermetic)` job has failed on
the last two pushes (`0f2811b`, `8e122ab`), both of which touched only
documentation and a workflow file. The Postgres job passes, and the full suite
passes locally (511 passed, 1 skipped). The cause is not yet known: reading the
failing log needs `gh auth login`, which nobody has run. **Do not publish an
image while a test job is red** — not because the failure is necessarily real,
but because "we shipped it with a red build and assumed" is the sentence you do
not want to be saying later. Diagnose it first; it is likely quick.

**Nothing has been published yet.** `ghcr.io/achindra2003/helix` does not exist
at any tag. Step 1 creates it.

**Nobody has ever run this image.** It builds in CI and is never started there.
Step 9 is the first execution of the built artifact in the project's history,
which is why it is written as an ordered list that stops at the first failure
rather than a paragraph.

---

## What you need first

- A GCP project with billing enabled.
- A domain name you can add an A record to. Caddy issues a Let's Encrypt
  certificate for it, so **DNS must point at the instance before the stack
  starts** — the ACME challenge is answered on port 80, and a name that does
  not resolve to this machine fails to issue rather than waiting.
- A Groq API key. See the note in step 7 — it is needed for verification even
  though the instance runs on the stub provider.

---

## The sizing problem, stated once

The measured application is **~570 MB** resident once anything semantic has run
(`DEPLOY-V1.md` has the table). The recorded plan is a free `e2-micro`, which
has **1 GB**. That measurement was taken with the app alone. This deployment
also runs Postgres and Caddy on the same instance:

| | |
|---|---|
| Helix | ~570 MB |
| Postgres (with `shared_buffers=64MB`, as configured) | ~120 MB |
| Caddy | ~20 MB |
| Debian + Docker daemon | ~150 MB |
| **Total** | **~860 MB of 1024 MB** |

It fits, and it is not comfortable — about 160 MB of margin, less than one
extra uvicorn worker and less than Postgres would take on its stock
`shared_buffers=128MB`. Two things follow, and neither is optional:

1. **The 2 GB swap file in step 4.** It converts a spike from an OOM kill into
   a slow request.
2. **`--workers 1`,** already baked into the image and commented there.

If the instance OOMs anyway, the fix is `e2-small` (2 GB, and no longer free)
rather than tuning — say so rather than trimming the app.

---

## Step 1 — publish the image *(Achindra's go-ahead; runs in CI, not on a machine)*

Requires the CI blocker above to be resolved first.

```bash
git tag v0.9.0-rc1
git push origin v0.9.0-rc1
```

`.github/workflows/release.yml` builds and pushes to GHCR. A pre-release tag
(anything with a hyphen) publishes only itself; `latest` is deliberately left
unclaimed until a real release, so nothing points strangers at an image that
has not been through step 9 yet.

**Then make the package public** — GHCR packages are private by default even
from a public repo, and the instance will fail to pull with an authentication
error that looks nothing like a permissions problem. GitHub → your profile →
Packages → `helix` → Package settings → Change visibility → Public.

*Verify:* `docker pull ghcr.io/achindra2003/helix:v0.9.0-rc1` from any machine
with no GitHub credentials.

## Step 2 — the instance

```bash
gcloud compute instances create helix-v1 \
  --machine-type=e2-micro \
  --zone=us-central1-a \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --tags=http-server,https-server
```

`e2-micro` is only free in `us-west1`, `us-central1` and `us-east1`. 20 GB of
disk is well beyond the ~2.5 GB image, and disk is the cheap axis — this
project has already lost a day to a full one.

## Step 3 — firewall

```bash
gcloud compute firewall-rules create helix-web \
  --allow=tcp:80,tcp:443 --target-tags=http-server,https-server
```

80 and 443 only. Nothing else needs to be reachable: the app and Postgres talk
over the compose network and publish no ports, which is the arrangement that
survives someone forgetting to close 8000.

## Step 4 — swap, then Docker

SSH in (`gcloud compute ssh helix-v1 --zone=us-central1-a`), then:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # survives reboot

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && exec newgrp docker
```

Swap first, deliberately. It is the step that stops being possible to do calmly
once the machine is under memory pressure.

## Step 5 — DNS

Point an A record for your domain at the instance's external IP
(`gcloud compute instances describe helix-v1 --zone=us-central1-a
--format='get(networkInterfaces[0].accessConfigs[0].natIP)'`), and wait for it
to resolve before step 8. `dig +short your.domain` answering with that IP is
the check.

## Step 6 — the repo and the configuration

The e2e verification scripts are **not in the image** (`.dockerignore` excludes
`frontend/app/e2e/`), so the checkout is not optional — step 9 needs it, and it
also needs Node.

```bash
sudo apt-get update && sudo apt-get install -y git nodejs
git clone https://github.com/Achindra2003/Helix.git && cd Helix
cp .env.prod.example .env
```

Then edit `.env`. Every value without a default will refuse to start the stack
rather than defaulting to something guessable. Generate the two secrets *on the
server* and reuse nothing:

```bash
openssl rand -base64 32     # once for JWT_SECRET, once for POSTGRES_PASSWORD
```

`JWT_SECRET` signs login tokens *and* derives the encryption of saved provider
keys. Changing it later logs everyone out and invalidates those keys — back it
up alongside the database, because a restore without it is a restore nobody can
log into.

## Step 7 — the provider key

Set `GROQ_API_KEY` in `.env` **even though `LLM_PROVIDER` stays `stub`.** This
looks contradictory and is not: `_KEY_REQUIRED` is `{"groq"}`, so the stub
provider needs no key for chat — but `ResolvedProvider.deep_llm` falls back to
the *server's* Groq key for Deep Reasoning regardless of provider
(`api/provider_settings.py`). With no key set, the paused-deep-run check in
step 9.3 cannot pass, and it is the check that matters most.

So: chat stays free and fake, the guided run is real. That is the right mix for
a verification pass.

## Step 8 — schema, then start

Order matters. `.env` sets `DB_AUTO_CREATE=false`, so the app does *not* create
its own tables; the schema is applied as an explicit step. Starting everything
at once would race the app against an empty database.

```bash
export HELIX_VERSION=v0.9.0-rc1

docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml run --rm helix alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

CI checks on every push that `alembic upgrade head` and the app's own
`create_all` produce the same schema on real Postgres, so this is a choice
about who controls the timing, not about which one is correct.

---

## Step 9 — verification, in this order, stopping at the first failure

This is where Stage A's withdrawn local checks land. They arrive together
because the disk failure moved them here, which is exactly the pile-up the
original ordering existed to prevent — so walk it slowly, and do not start the
next check until the previous one passes.

### 9.1 It is serving, and it fits

```bash
curl -sS https://your.domain/health
docker stats --no-stream
```

*Expect:* `/health` answers 200 over HTTPS, and the `helix` container sits
around **570 MB**. Send one grounded chat message through the UI first — MiniLM
is not resident until something semantic has run, so a reading taken at rest
flatters the number. This confirms on Linux a figure measured on Windows.

*If memory is much higher:* stop and report it. It is the assumption the whole
instance size rests on.

### 9.2 State survives replacing the container

```bash
cd frontend/app
HELIX_E2E_API=https://your.domain node e2e/persistence.mjs seed /tmp/state.json
cd ../.. && docker compose -f docker-compose.prod.yml down && \
  docker compose -f docker-compose.prod.yml up -d
cd frontend/app
HELIX_E2E_API=https://your.domain node e2e/persistence.mjs verify /tmp/state.json
```

Four claims: the account survives, **a token issued before the restart still
works**, the thread is there, and a guided run paused before the restart can
still be steered. The token is the sharp one — phase two deliberately does not
log in again, because a fresh login would pass even against a regenerated
signing secret, which is precisely the failure the `/data` volume exists to
prevent.

*This has been rehearsed* against a restarted local stack and all four passed.
A failure here is about the container or the volume, not about the script.

### 9.3 The three room journeys, against Postgres

```bash
cd frontend/app
HELIX_E2E_API=https://your.domain \
HELIX_E2E_MCP_HOST=host.docker.internal \
  node e2e/rooms.mjs
```

The parity run that has never happened. These pass on SQLite today, so anything
failing here is a genuine dialect difference.

`HELIX_E2E_MCP_HOST` must name an address **the container can reach**, not one
you can. Room two starts a stub MCP server on the VM and registers it, and the
*app* then calls back into it — `127.0.0.1` would be the container itself.
`docker-compose.prod.yml` maps `host.docker.internal` to the host gateway for
exactly this.

### 9.4 A real registration

Register through the UI over HTTPS, make a workspace, send a message, upload a
document. The install a stranger would do, done once by us — and the only check
here that exercises the built frontend rather than the API.

---

## What to report back

For each of 9.1–9.4: passed, or the exact output. Plus the `docker stats`
figure, since it either confirms or overturns the instance sizing.

If anything fails, `docker compose -f docker-compose.prod.yml logs helix` is
the first thing to capture, before restarting anything — a restart is often
what destroys the evidence.

---

## Traps, each of which has already caught someone

- **Do not build on the instance.** No `docker compose up` with the other two
  compose files; both carry a `build:` and the build needs several GB the box
  does not have. `docker-compose.prod.yml` has no build section at all, which
  is its entire reason for existing.
- **`postgresql+asyncpg://`, never `postgresql://`.** The plain form selects
  psycopg2, which is not installed in the image, and the app dies at startup.
  A previous compose file had exactly this bug.
- **Don't restart repeatedly to fix a TLS problem.** Let's Encrypt allows 5
  certificates per domain per week, and a restart-heavy afternoon can spend
  them. Check `docker compose logs caddy` and fix the cause — usually DNS not
  yet resolving to this instance.
- **`HELIX_VERSION` is required and should never be `latest`.** An instance
  that changes version on the next restart is one nobody can debug afterwards.

---

## After it is up

Not in scope for this pass, in the plan's order: RLS policies (`DEPLOY-V1.md`
A5 — needs this live instance, and is deliberately sequenced after the app has
run on Postgres so a zero-row query has two possible causes rather than three),
then `pg_dump` on a cron **with one restore actually performed** — a backup
nobody has restored is a belief, not a backup — then UptimeRobot on `/health`,
then Sentry.

The `v1.0.0` tag comes after step 9 passes, not before.
