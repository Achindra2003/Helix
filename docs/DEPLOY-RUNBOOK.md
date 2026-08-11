# Deploy runbook — Helix v1 on a GCP instance

The executable half of `DEPLOY-V1.md`. That document argues about ordering and
risk; this one is a list of commands for someone who was not part of those
conversations. Where the two disagree, this file is what to run and that one is
why.

**Read the whole of "Before you start" and "What this costs" before typing
anything.** Two of the steps below cannot be undone cheaply, one flag decides
whether this instance is free, and one setting locks the instance out for good
if it is changed too early.

---

## Who does what

| | |
|---|---|
| **Achindra** | GCP project + billing, DNS, and the go-ahead to publish the image (it creates a package under his GitHub account). `gcloud auth login` is interactive and has to be run by whoever owns the account. |
| **Mansoor** | Everything on the machine: instance, Docker, the stack, and the verification in step 9. |
| **Already done** | The image builds in CI, the full test suite passes against real Postgres, and the migrations have been applied to a real server. Nothing below should surface a code defect. If it does, stop and say so — that is a finding, not a step to work around. |

---

## Before you start

**CI is green at HEAD.** All four jobs pass on `6738204`. An earlier note here
called this a blocker; it no longer is.

One thing to know rather than to act on: the `Backend tests (261, hermetic)`
job failed on `0f2811b` and `8e122ab` — two commits that touched only a
workflow file and documentation — and then passed on `6738204`, which is also
inert. In both failures the dependency install *succeeded* and the test step
ran its full ~165 s, the same as a green run, so this is not a broken
environment; it is one or more tests that fail intermittently. Nobody has named
which, because reading a failing job's log needs `gh auth login` and that has
not been run. It is worth naming before `v1.0.0` and it does not block anything
below.

**The rule stands: do not publish an image while a test job is red.** Not
because a given failure is necessarily real, but because "we shipped it with a
red build and assumed" is not a sentence you want to be saying afterwards.
Re-check before step 1 rather than trusting this paragraph.

**The image is published.** `ghcr.io/achindra2003/helix:v0.9.0-rc1` exists and
is anonymously pullable as of 11 August — step 1 is done, and Mansoor starts at
step 2.

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
  not resolve to this machine fails to issue rather than waiting. If you do
  not own one, see step 5: a free subdomain works and needs no change to the
  `Caddyfile`.
- A Groq API key. See the note in step 7 — it is needed for verification even
  though the instance runs on the stub provider.

### What this costs

The intended answer is nothing, and it is nearly true. `e2-micro` in the three
listed regions, and 20 GB of `pd-standard`, are inside Google's always-free
allowance; the registry, CI, TLS, and the Groq and Tavily free tiers cost
nothing. Two things sit outside it, and both are easy to miss:

- **The external IPv4 address**, roughly $3 a month. Google bills every public
  IPv4 attached to a running instance, free-tier machine or not. There is no
  way around it while the instance is reachable from the internet — deleting
  the instance after the evaluation window is the lever, not tuning.
- **The boot disk**, if step 2's `--boot-disk-type` flag is dropped.

The always-free tier also requires an **upgraded (paid) billing account** with
a card on file. Trial credits expire, and when they do an un-upgraded account
stops its resources — which for a demo URL tends to happen exactly when
somebody finally opens it. Set a $1 budget alert while you are in the billing
console.

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

Confirm CI is green on the commit being tagged before running this — see
"Before you start". It was green at `6738204`; that is a fact with a date on
it, not a standing guarantee.

```bash
git tag v0.9.0-rc1
git push origin v0.9.0-rc1
```

`.github/workflows/release.yml` builds and pushes to GHCR. A pre-release tag
(anything with a hyphen) publishes only itself; `latest` is deliberately left
unclaimed until a real release, so nothing points strangers at an image that
has not been through step 9 yet.

**Package visibility needed no manual step.** An earlier draft of this file
said GHCR packages are private by default and must be flipped in the UI. That
is true of a package created by a personal access token; it is not true here.
This one is published by the workflow's `GITHUB_TOKEN` from a public
repository, so it inherited that repository's visibility and was pullable
anonymously the moment it existed. Checked rather than assumed — see below.
If a future package does come out private, the fix is GitHub → profile →
Packages → `helix` → Package settings → Change visibility → Public.

**Verified after the fact, 11 August**, against the registry with an anonymous
token and no GitHub credentials:

| | |
|---|---|
| Anonymous pull | works (`200` on the manifest and the tag list) |
| Tags published | `v0.9.0-rc1` — and nothing else |
| `:latest` | `404`. The pre-release logic works in practice, not just on paper |
| Platform | `linux/amd64` only, which is what an `e2-micro` is |
| Download size | **~617 MB** compressed across 12 layers |

That last number is the one to plan the VM's first minutes around: ~617 MB is
what crosses the network, and the *unpacked* image on disk is several times
that — comfortably inside step 2's 20 GB, and nowhere near quick on a shared
vCPU. A slow first `docker compose up` is expected and is not a fault.

*Re-verify at any time:* `docker pull ghcr.io/achindra2003/helix:v0.9.0-rc1`
from a machine with no GitHub credentials.

## Step 2 — the instance

```bash
gcloud compute instances create helix-v1 \
  --machine-type=e2-micro \
  --zone=us-central1-a \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-standard \
  --tags=http-server,https-server
```

`e2-micro` is only free in `us-west1`, `us-central1` and `us-east1`. 20 GB of
disk is well beyond the ~2.5 GB image, and disk is the cheap axis — this
project has already lost a day to a full one.

**`--boot-disk-type=pd-standard` is not optional if this is meant to be free.**
`gcloud` defaults new instances to `pd-balanced`, and the always-free
allowance covers *standard* persistent disk only — 30 GB-months of it, so 20 GB
sits inside it. Omit the flag and the instance still works; it just quietly
bills for the disk, which is the kind of charge nobody notices until the month
turns.

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

**This instance uses [DuckDNS](https://duckdns.org)** (decided 11 August). It
is ordinary public DNS, so Caddy answers the same HTTP-01 challenge on port 80
and the `Caddyfile` needs no change at all — put `<name>.duckdns.org` in
`HELIX_DOMAIN` and continue. Swapping to a real domain later is that one line
and a restart.

Useful ordering: the subdomain can be **claimed before the instance exists**,
and pointed at an IP afterwards from the DuckDNS page (or by hitting its update
URL from the VM). So the name does not have to wait on step 2, and step 2 does
not have to wait on whoever owns the DuckDNS account — only the A-record update
sits between them, and it propagates in about a minute.

Avoid the wildcard-DNS services that encode an IP in the hostname
(`nip.io`, `sslip.io` and friends). They resolve fine, but everyone shares one
registered domain, so Let's Encrypt's per-domain rate limit is frequently
already spent by strangers and issuance fails for reasons that look like a
problem with this instance.

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

Registering also seeds an example workspace automatically (`auth.py` calls
`seed_example_workspace` after the account commits), so the first screen is not
empty and there is nothing to seed by hand.

---

## Step 10 — decide who can sign up *(after step 9, never before)*

`.env` ships `ALLOW_REGISTRATION=true`, and it has to start that way. With
registration closed, `/auth/register` demands a valid invite, and invites come
from workspace owners — on an empty database nobody can issue one, so closing
signup before anyone has registered locks the instance out for good.

So once the accounts that should exist do exist, make the call:

| | |
|---|---|
| **Leave it open** | Right for a public demo anyone should be able to try. |
| **`ALLOW_REGISTRATION=false`,** then `docker compose -f docker-compose.prod.yml up -d` | Right for a real instance. Existing users keep working; new ones need an invite link. |

Not a formality. `GROQ_API_KEY` is the *server's* key and Deep Reasoning falls
back to it for every user regardless of provider, so on an open instance anyone
who finds the URL can spend it. Whichever you pick, pick it deliberately.

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
