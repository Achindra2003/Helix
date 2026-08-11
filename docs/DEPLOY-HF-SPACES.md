# Deploy runbook — Helix on Hugging Face Spaces

The live runbook. `DEPLOY-RUNBOOK.md` describes a GCP instance and is retained
for its reasoning, not for its commands — **this is the file to follow.**

Read "Before you start" and "Two checks are expected to fail" in full before
running anything. The second one exists so that a known limitation is not
reported as a bug at eleven at night.

---

## Why not GCP

Not a preference. Google Cloud and Azure both required a payment method that
could not be completed: the card was declined, GCP's UPI alternative wanted a
₹1000 prepayment with reports of accounts being suspended straight after
paying it, and Azure for Students failed institutional email verification.
Two dead ends is where this stopped being worth more attempts.

Spaces needs no card and no institutional verification, and its free CPU tier
is 2 vCPU and **16 GB of RAM**. That last number ends an argument this project
has been having since July: the measured ~570 MB working set, the 2 GB swap
file, `shared_buffers=64MB`, the "it fits and it is not comfortable" table —
all of it was a fight for 160 MB of margin on a 1 GB box. There is no fight
here.

---

## Who does what

| | |
|---|---|
| **Mansoor** | All of it, accounts included — Hugging Face, Neon and Groq are three email sign-ups and none takes a card. Nothing below needs anyone else. |
| **Achindra** | Nothing, once this starts. One thing to know: the Space lives under whoever's account creates it, so the public URL will read `huggingface.co/spaces/<mansoor>/helix`. Add Achindra as a Space collaborator (Settings → Collaborators) so the link does not depend on one person's account. |
| **Already done** | The image is published and CI-green: `ghcr.io/achindra2003/helix:v0.9.0-rc1`, anonymously pullable, linux/amd64, ~617 MB. The Space does not build Helix — it runs that artifact. |

---

## Before you start

**Nobody has ever run this image.** It builds in CI and is never started
there. Step 5 is the first execution of the built artifact in this project's
history, which is why it is an ordered list that stops at the first failure
rather than a paragraph.

**What is different from every other deployment we planned.** A free Space has
**no persistent disk**. Nothing written inside the container survives a
restart. Three consequences, and each is handled below rather than discovered:

1. The database cannot live in the container. It goes to Neon (step 1).
2. `JWT_SECRET` must be set explicitly. The image will otherwise generate one
   to `/data/.jwt_secret`, which is fine until the Space restarts and everyone
   is logged out — the exact failure the Docker volume existed to prevent.
3. A **paused** deep run will not survive a restart. See below.

---

## Two checks are expected to fail

Both are properties of this hosting choice, not defects. Report them as
"expected" — and if either *passes*, say so, because that would mean something
is not what we think it is.

**1. `persistence.mjs` check 4 — the paused deep run.** Helix checkpoints a
paused guided run to a SQLite file at `CHECKPOINT_PATH`, which is on the
container's ephemeral disk. Restart the Space and that file is gone. The other
three checks — the account, a token issued before the restart, the thread —
must all still pass, because those live in Neon. If *they* fail, that is a
real finding.

*The fix, if we want it later:* point LangGraph's checkpointer at Postgres
instead of a file. That would make paused runs durable without any disk at
all — more robust than the VM plan was. It is a dependency and a change to
`api/checkpointing.py`, so it is separate work, not something to attempt
mid-deploy.

**2. `rooms.mjs` room two — the MCP tool journey.** That test starts a stub MCP
server on the machine running the script and registers it, and the *app* then
calls back into it. The app is inside Hugging Face's infrastructure and cannot
dial back into a laptop. Rooms one and three must pass.

This limits the *test*, not the product: a real, publicly reachable MCP server
works normally.

---

## What you need on your machine

**`git` and Node 20 or newer. That is the whole list.**

Worth stating because the previous plan needed much more, and because the
instinct on reading "deploy" is to install Docker. There is nothing to build
here: Hugging Face builds the Space, and the Space pulls an image that already
exists. No Docker, no Python, no database client, and no `npm install` — both
verification scripts import only Node built-ins, so a clone plus `node` runs
them.

```bash
git clone https://github.com/Achindra2003/Helix.git
cd Helix
```

That checkout is needed twice: `deploy/hf-space/` holds the two files the Space
runs (step 3), and `frontend/app/e2e/` holds the verification scripts (step 6),
which are deliberately excluded from the image.

---

## Step 0 — the three accounts

All three are email sign-ups. None asks for a card, and none needs
institutional verification — which is the entire reason this deployment is
here rather than on a VM.

| | |
|---|---|
| **huggingface.co** | Hosts the Space. Sign up, verify the email, done. |
| **neon.tech** | Free Postgres. "Sign up with GitHub" is the fastest route. |
| **console.groq.com** | Free API key, used in step 4. Create it under *API Keys* and copy it immediately — Groq shows it once. |

Fifteen minutes, and none of it depends on anyone else.

---

## Step 1 — the database

Create a Neon project. On the dashboard, copy the connection string, then
change two things about it.

Neon hands you this shape:

```
postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

Helix needs this shape:

```
postgresql+asyncpg://user:pass@ep-xxx.region.aws.neon.tech/neondb?ssl=require
```

Both edits are required and neither is cosmetic:

- **`postgresql+asyncpg://`**, not `postgresql://`. The plain form selects
  psycopg2, which is not installed in the image, and the app dies at startup.
- **`?ssl=require`**, not `?sslmode=require`. `sslmode` is libpq's spelling;
  asyncpg does not accept it and raises on connect.

**Use the direct endpoint, not the pooled one.** If the hostname contains
`-pooler`, take the other one. Neon's pooler runs in transaction mode, which
breaks asyncpg's prepared-statement cache — the symptom is an intermittent
`prepared statement "__asyncpg_stmt_N__" does not exist` that appears only
under concurrency and passes every test you throw at it. Helix has a
`DB_POOLED=1` setting that disables those caches for exactly this case, but
one worker on a demo instance does not need a pooler, and the direct endpoint
is one fewer thing to be wrong.

## Step 2 — create the Space

huggingface.co → **New Space**.

| Field | Value |
|---|---|
| Owner | your account |
| Space name | `helix` |
| License | MIT |
| SDK | **Docker** → *Blank* |
| Hardware | **CPU basic** (free) |
| Visibility | Public |

## Step 3 — add the two files

The Space is a git repository. Clone it and copy in the two files from
`deploy/hf-space/` in this repo:

```bash
git clone https://huggingface.co/spaces/<your-username>/helix
cd helix
# copy deploy/hf-space/Dockerfile and deploy/hf-space/README.md here
git add Dockerfile README.md
git commit -m "Run the published Helix image"
git push
```

The push starts a build. It will fail to start until step 4 gives it a
database — that is expected, and not worth debugging.

You can also paste both files through the web UI if you would rather not clone.

## Step 4 — secrets and variables

Space → **Settings** → *Variables and secrets*.

As **secrets** (hidden after saving):

| Name | Value |
|---|---|
| `DATABASE_URL` | the converted Neon string from step 1 |
| `JWT_SECRET` | `openssl rand -base64 32` — generate a fresh one, reuse nothing |
| `GROQ_API_KEY` | your Groq key |

As **variables** (visible, and it helps that they are):

| Name | Value | Why |
|---|---|---|
| `DB_AUTO_CREATE` | `true` | There is no shell in which to run `alembic upgrade head`, so the app creates its own schema at boot. CI checks on every push that migrations and `create_all` produce the same schema on real Postgres, so this is a choice about who applies it, not about which is correct. |
| `LLM_PROVIDER` | `stub` | Every screen is explorable on a fake model. Switch to `groq` once step 5 passes. |
| `ALLOW_REGISTRATION` | `true` | It cannot start any other way — closed registration needs an invite, invites come from workspace owners, and on an empty database nobody can issue one. Revisit after step 5. |

`JWT_SECRET` signs login tokens **and** derives the encryption of saved
provider keys. Changing it later logs everyone out and invalidates those keys.
Keep a copy somewhere other than the Space.

**`GROQ_API_KEY` is needed even though `LLM_PROVIDER` is `stub`.** This looks
contradictory and is not: the stub provider needs no key for chat, but
`ResolvedProvider.deep_llm` falls back to the server's Groq key for Deep
Reasoning regardless of provider (`api/provider_settings.py`). Without it, the
deep-run parts of step 5 cannot run at all.

Saving a secret rebuilds the Space. Wait for **Running**; the first build pulls
~617 MB and unpacks it, so give it several minutes.

---

## Step 5 — verification, in this order, stopping at the first failure

The Space's public API base is `https://<your-username>-helix.hf.space`
(the page at `huggingface.co/spaces/<username>/helix` is the wrapper around
it). Use the `.hf.space` URL for every command below.

The e2e scripts are **not in the image**, so this needs a checkout of the main
repo and Node:

```bash
git clone https://github.com/Achindra2003/Helix.git && cd Helix/frontend/app
```

### 5.1 It is serving

```bash
curl -sS https://<username>-helix.hf.space/health
```

*Expect:* 200, and `durable_runs` present in the body. Memory is visible in the
Space's own metrics rather than `docker stats` — note the figure if it is
shown, but nothing depends on it now. The 570 MB question mattered against
1 GB; against 16 GB it is a curiosity.

### 5.2 State survives a restart

```bash
HELIX_E2E_API=https://<username>-helix.hf.space node e2e/persistence.mjs seed /tmp/state.json
```

Then Space → Settings → **Restart this Space**. Wait for **Running**.

```bash
HELIX_E2E_API=https://<username>-helix.hf.space node e2e/persistence.mjs verify /tmp/state.json
```

*Expect:* checks 1–3 pass, check 4 fails as described above. The sharp one is
check 2 — a token issued *before* the restart still works, which is what proves
`JWT_SECRET` came from the environment rather than being regenerated. Phase two
deliberately does not log in again, because a fresh login would pass even
against a regenerated signing secret.

### 5.3 The room journeys

```bash
HELIX_E2E_API=https://<username>-helix.hf.space node e2e/rooms.mjs
```

*Expect:* rooms one and three pass. Room two fails on the MCP callback, as
described above. These pass on SQLite today, so anything failing in rooms one
or three is a genuine Postgres dialect difference and worth stopping for.

### 5.4 A real registration

Register through the UI over HTTPS, make a workspace, send a message, upload a
document. The install a stranger would do, done once by us — and the only check
that exercises the built frontend rather than the API. Registering also seeds
an example workspace automatically, so the first screen will not be empty.

---

## Step 6 — turn the real model on

Once 5.1–5.4 are as expected, set `LLM_PROVIDER=groq` and let it rebuild. Send
one message and run one Deep Reasoning run against the real model.

Chat now runs on `openai/gpt-oss-20b` and deep reasoning on
`openai/gpt-oss-120b` — Groq retired the Llama models Helix used to default to
on 16 August 2026 for free-tier keys. If you see a model-not-found error, the
key or the model name is stale, not the code.

---

## What to report back

For each of 5.1–5.4: passed, expected-fail, or the exact output. If anything
outside the two known failures goes wrong, capture the Space's **Logs** tab
before restarting anything — a restart is often what destroys the evidence.

---

## Traps

- **Do not change `app_port`.** Spaces default to 7860; the image serves on
  8000. With the default the Space builds fine, starts fine, and then times out
  waiting for a port nothing is listening on.
- **Do not build Helix from source in the Space.** The Dockerfile is one
  `FROM` line on purpose — it runs the artifact CI published. A source build
  would be a different image nobody tagged.
- **Do not use Neon's `-pooler` hostname** without also setting `DB_POOLED=1`.
- **Free Spaces sleep after inactivity** and wake on the next visit, with a
  cold start. That is normal. It also means a paused deep run can be lost
  without anyone pressing restart.
- **`sslmode` is not `ssl`.** Copying Neon's string unedited fails at startup
  with an asyncpg error that reads nothing like a configuration problem.

---

## After it is up

In order: decide `ALLOW_REGISTRATION` now that accounts exist; move the
checkpointer to Postgres if paused runs surviving restarts matters; then
UptimeRobot on `/health`, and the `v1.0.0` tag.

Backups are Neon's problem rather than ours here, which removes `pg_dump` on a
cron from the list — but not the rule behind it. Take one export and restore it
somewhere once, because a backup nobody has restored is a belief, not a backup.
