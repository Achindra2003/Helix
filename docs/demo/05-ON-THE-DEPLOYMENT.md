# 05 — Running the demo on the live instance

| | |
|---|---|
| **Helix** | <https://achindra2003--helix-serve.modal.run> |
| **MCP server** (room 2 only) | <https://achindra2003--helix-mcp-stub-serve.modal.run> |

The other four files in this directory assume a laptop. This one is the same
three rooms performed against the deployed instance — and unlike every earlier
draft of this page, **all three of them hold there.**

```
$ HELIX_E2E_API=https://achindra2003--helix-serve.modal.run \
  HELIX_E2E_MCP_URL=https://achindra2003--helix-mcp-stub-serve.modal.run \
  node e2e/rooms.mjs

── Room 1 — a general team ───  14/14 ok
── Room 2 — a dev team ───────  19/19 ok
── Room 3 — a research group ─  10/10 ok

all three rooms hold
```

That is the whole claim of this page, and it is reproducible with one command.

One check the rooms cannot make, because they only ever speak HTTP:

```
$ node e2e/realtime-hold.mjs https://achindra2003--helix-serve.modal.run 60

ok  held 60s — 1 presence frame(s), 5 pong(s)
```

Run both. A host that serves every request correctly and silently drops
WebSockets passes the rooms suite clean — which is precisely what happened
here once, and cost the demo its best moment without a single failing
assertion.

---

## The history, because two earlier answers were wrong

This page has been rewritten three times, and the wrong turns are worth keeping
because each one is a plausible mistake somebody else will make.

**First answer — "a free host cannot run the neural embedder."** Inferred from a
real measurement (~570 MB resident once MiniLM has run) and never tested. Wrong:
the embedder ran fine on a free 512 MB host. See the discriminator below, which
is still the sharpest evidence on this page.

**Second answer — "it is not memory, it is database connections."** The Render
logs showed `/health` failing inside `db_ping` → `asyncpg.connect` →
`TimeoutError`, with no OOM line anywhere. That reading missed the decisive
line: `INFO: Started server process [1]` a minute after the tracebacks is PID 1
in a *replacement container*. The database timeouts were a dying event loop, not
a cause.

**The actual answer — the box was too small, exactly as `DEPLOY-RUNBOOK.md`
sized it.** ~570 MB of application on 512 MB with no swap. It never fit; what
varied was only how long until something asked for memory that was not there.
Registration asked hardest, because it embeds a batch *and* opens the most
connections at once.

**The fix was a bigger box, not code.** On Modal with 2 GB, registration returns
`201` in 29 seconds and `/health` answers in ~1 s immediately afterwards. Same
application, same database, same code — the request that reliably killed the
free instance is now merely slow.

Keep this in mind when reading the rest: everything here is a *hosting* result.
Nothing about the product changed.

---

## What was verified, and how

The rooms suite above covers 43 assertions end to end. These are the individual
measurements behind the interesting ones.

| Check | Result | How |
|---|---|---|
| Serving | `200`, `provider: groq`, `durable_runs: true` | `GET /health` |
| Cold start | ~25 s | first request after idle |
| Warm response | ~1.0 s | `GET /health` ×3 |
| **Registration** | **`201` in 29 s**, health ~1 s immediately after | `POST /api/auth/register`, health polled |
| **Neural embedder resident** | **yes** | see the discriminator below |
| Grounded answer + citations | correct, and still on the node after re-read | room 3, checks 3–5 |
| Citation is a reference, not a filename | `Lewis et al. (2020)` | room 3, check 5 |
| **MCP discovery** | 3 tools found on the hosted stub | room 2, `POST …/mcp/{id}/sync` |
| **Approval gate** | a sensitive call pauses the run; approving streams the continuation | room 2, checks 11–12 |
| **Tool ledger** | `{tool: get_pull_request, source: mcp:github, status: ok, calls: 1, avg_latency_ms: 404}` | `GET …/usage` |
| **Observer role** | can leave a margin note, **cannot** address the model | room 3, checks 8–9 |
| **Realtime WebSocket** | held **60 s**, presence frame on connect, pongs throughout | `wss://…/ws/workspaces/{id}?token=` |
| Explore ways, voting, adoption, ledger | all hold | room 1, checks 7–11 |
| Decision export = the ADR | carries the verdict, the rejected alternative, **and** the change it was about | rooms 1 and 2 |
| `@mention` → notice | holds | room 1, checks 4–5 |

### The embedder discriminator

Worth keeping even though the conclusion it overturned is now two revisions old,
because it is the only proof on this page that does not depend on trusting a
log.

The search API has no `mode` switch, so the dense signal was isolated by
construction. A query sharing **no content word** with the corpus scores ~0 on
BM25 and cannot clear `grounding_lexical_floor` (0.30 squashed) — so any hit
returned had to come from `dense > grounding_floor` (0.20).

```
overlap control    "mooring lines eastern pier corrosion"                         1 hit   0.4897
zero-overlap #1    "who has the power to stop boats from sailing when the sea..."  1 hit   0.3554
zero-overlap #2    "used lubricant disposal from the motor compartment needs..."   1 hit   0.3024
unrelated control  "customer churn in the subscription billing dashboard"          0 hits
```

`LexicalEmbedder` is a hashed bag-of-words (`engine/ouroboros/memory.py`, md5
per token). It is *orthogonal* to tokens it has never seen, so it cannot produce
rows 2 and 3. **MiniLM is resident and working.** A deep run ending
`stop_reason: "converged"` is the independent confirmation — convergence
calibrates to ~0.90 neural against ~0.78 lexical, so the run halted on meaning
rather than on budget.

---

## What still differs from local

**One thing, and it is not a product limit.**

> **Corrected 14 August.** This section used to open with *"deep runs are
> capped at 120 seconds here, not 300"* — the deployment shipped a smaller
> reasoning budget than the product has, to stay under Modal's 150-second
> request ceiling. That was paying for a hosting limit with a product
> capability, and it is no longer done. The client treats a cut stream as a
> dropped transport rather than a finished run and reattaches from the last
> event it read, so a run may outlive any number of requests. The budget on the
> deployment is the product's own again.

Modal still severs any HTTP request at 150 seconds — that part was never
negotiable, and it is why the deployment runs on `asgi_app`: the alternative,
`web_server`, has a 3600-second ceiling but does not carry WebSockets (measured
— the socket opens and closes within two seconds, while the identical build
holds it open locally). Realtime was worth more than the request ceiling.

What changed is that the ceiling stopped costing anything. `GET
/conversations/deep/runs/{id}/stream?after=N` replays a run's event log from an
index and then follows live, so a client that has read N events carries on from
exactly there. Verified against this URL by `e2e/deep-reattach.mjs`: a run whose
reader is dropped mid-flight keeps executing, resumes with nothing repeated and
nothing lost, and writes its answer.

```
$ node e2e/deep-reattach.mjs https://achindra2003--helix-serve.modal.run

ok  the run outlived its reader (status: running)
ok  reattaching from index 4 is accepted
ok  the continuation does not replay what was already read
ok  the run's `complete` frame arrives on the reattached stream
```

**Paused deep runs are session-scoped, and `/health` will lie to you about it.**
The endpoint reports `durable_runs: true`, which means only *"the checkpointer
is not `MemorySaver`"* (`api/checkpointing.py:126`). It is the SQLite saver
writing to `CHECKPOINT_PATH` on a container filesystem with no volume attached.
Within one container it is genuinely durable; when the container is released
after idle, that file goes with it. Pause and resume inside your session and it
works. Pause it and come back tomorrow and it is gone.

Accounts, threads, branches, documents, chunks, embeddings, citations and
decisions all live in Postgres and are unaffected.

*If you want this fixed:* mount a `modal.Volume` at `/data` in
`deploy/modal/app.py`. It is deliberately not done — Modal Volumes are
documented as write-once/read-many with last-write-wins semantics, which is a
poor host for a SQLite file, and the demo does not need it.

**What used to be on this list and no longer is:** the MCP callback. The stub is
hosted now (below), so room 2 runs against the deployment in full — the
allowlist, the approval gate, the ledger and Review mode. No previous
deployment could do any of that.

---

## The two services

Helix and the MCP stub are separate Modal apps on purpose. The stub is a prop —
you point at it, rewrite a description mid-demo, throw it away — and coupling
its lifecycle to the product's would mean redeploying Helix to change a tool
description.

```bash
modal deploy deploy/modal/app.py        # Helix
modal deploy deploy/modal/mcp_stub.py   # the demo MCP server
```

Both are pinned to `max_containers=1`, which is not a cost decision. Presence
and workspace fan-out are an in-process dict (`api/realtime.py`), and
`RunManager` is a module singleton; a second container would split one workspace
into two rooms that cannot see each other. The stub is pinned for the same class
of reason — `/drift` must rewrite the description that the *next* `tools/list`
returns.

**To redeploy after a code change:** tag a release, let
`.github/workflows/release.yml` build and push to GHCR, then change `IMAGE_TAG`
in `deploy/modal/app.py` and run `modal deploy` again. That is the whole
procedure.

---

## Pre-flight

- [ ] Open the URL **five minutes early** and send one message. The container
      scales to zero when idle, so the first visitor pays ~25 s of cold start.
      Never let that happen on stage.
- [ ] Hit the **MCP stub's URL** too, for the same reason *(room 2 only)*.
- [ ] Two browser profiles, already logged in, side by side. Still
      non-negotiable, and now easier: window B just opens the URL. No LAN
      address, no `ipconfig`.
- [ ] Register the stub at `SETUP → Tool servers (MCP) → + Add a server`, auth
      value empty *(room 2 only)*.
- [ ] One rehearsal deep run spent at most — every visitor shares one free Groq
      key unless they bring their own. See "who pays".
- [ ] Know the one honest answer: paused runs are session-scoped here.

Unlike the earlier drafts of this page, **you may register accounts and upload
documents live.** That was forbidden on the 512 MB instance and it is fine here;
both were re-tested on Modal specifically.

There is no `.env` to hide, no `start-helix.bat`, no third window. That is the
whole advantage — **you can hand out the link and people can follow along on
their own laptops**, which no local demo can do.

---

## Room 1 — general team

**Runs unchanged.** Follow [`01-GENERAL-TEAM.md`](01-GENERAL-TEAM.md) beat for
beat. Explore ways, approval voting, withdrawal, the decisions ledger and the
export all pass on the deployment.

One note: **resurfacing needs ≥18 characters typed and clears a 0.33 relevance
floor.** It is semantic and the embedder is real here, so it works — but a short
question on stage still silently does nothing. Same warning as local.

## Room 2 — dev team

**Runs unchanged, once the stub is registered.** Follow
[`02-DEV-TEAM.md`](02-DEV-TEAM.md).

This is the room that gained the most. Verified live, hosted-to-hosted:
discovery finds three tools; they arrive `sensitive: true` and `allowed: false`;
the owner sees the description verbatim; the agent reaches for
`get_pull_request`; the sensitive call **pauses for a human**; approving it
streams the continuation; the call lands in the ledger at 404 ms.

Beat 7 works too: open `<stub URL>/drift` in a tab mid-demo, refresh the server
card, and the *"description changed — not offered to the model"* warning fires.
Two adjustments from the local script:

- The stub's request log is in Modal's dashboard, not a window on your screen.
  Have it open on a second monitor if you want to show calls arriving.
- The stub scales to zero as well. Wake it during pre-flight.

## Room 3 — research group

**Runs at full strength.** Follow
[`03-RESEARCH-GROUP.md`](03-RESEARCH-GROUP.md).

**Substitution:** there is no seeded eRisk workspace — `research@christ.edu`
does not exist on the deployment. Upload a paper live instead, which is a better
demo anyway: an audience that watches a PDF become a citable corpus in front of
them believes it more than one that was already there. Fill in the metadata
(author, year, title, identifier) so `cite_as` is shared by the citation chip,
the exports and the model's context — verified live, and the stored citation
reads `Lewis et al. (2020)` rather than a filename.

Then the spine holds as written: grounded question → citation chips → **reload
and the evidence is still attached to the claim** → export → invite a supervisor
as **Observer** who can leave a note the model never reads. That last one is
verified on the deployment, having been untestable while the old instance kept
falling over.

**Caution:** escalate to the deep run and let it finish. Do not pause it and
walk away — see the paused-run note above.

---

## Who pays

Registration is **open**, and every workspace that has not set its own provider
inherits the server's single free Groq key (`provider_settings.resolve()` →
`_server_default()`). Anyone with the link spends that quota, and
`openai/gpt-oss-120b` deep runs are the hog.

Per-workspace spend is bounded — `deep_runs_per_workspace: 2`, a 200k token
budget and a 300 s deadline per run — so no single team runs away with it.
Thirty teams sharing one key still can.

The built-in answer, and the thing to say out loud if anyone asks how this
scales: **each workspace owner pastes their own free Groq key** at
`SETUP → Provider`. Per-workspace, encrypted at rest, owner-governed. It is
already built; it just is not presented as the funding model anywhere.

**Modal's own cost** is not the constraint people expect. The Starter plan
carries $30/month of credits and the container is billed per second only while
it is up — scaled to zero between demos, this runs for a rounding error. Keeping
it permanently warm at 1 core / 2 GB would be roughly $45/month, which is the
only way to exceed the free credits.

One decision still open, and it does not block a demo: **`ALLOW_REGISTRATION`**
is right for a public demo and wrong for a durable instance. Note the ordering
constraint from `DEPLOY-V1.md` C4 — it can only be closed *after* accounts
exist, or the instance locks itself out permanently.

---

## When something goes wrong

| Symptom | Cause | What to do |
|---|---|---|
| First page load hangs ~25 s | Container had scaled to zero | Expected. This is why pre-flight says open it five minutes early. |
| A reply errors mid-demo | Groq free-tier quota, shared across every visitor | `SETUP → Provider`, paste a workspace key. Say the BYO line — it is a feature, not a save. |
| Grounding returns "nothing relevant" | The relevance floor, working | Say so. An unrelated question cannot drag the knowledge base into its prompt. |
| A paused deep run cannot be steered | The container was released and the checkpoint file went with it | Expected here, not a product limit. Finish deep runs within the session. |
| MCP server card shows an error | The stub scaled to zero, or the registered URL is a loopback address | Open the stub's URL to wake it. The registered URL must be its public one. |
| A teammate's tokens do not appear | Both windows must have the same thread open | Same as local. The socket is verified working. |

---

## The one line to have ready

Two limits, and both are the *hosting plan* rather than the product: a hosted
instance cannot dial back into your laptop, and a 512 MB instance cannot hold a
570 MB application.

Neither survives contact with a box the right size. On Modal the embedder is
resident, deep runs converge on meaning, realtime is proxied, agent tool calls
land in the ledger, the approval gate holds, and all three rooms pass end to
end. The MCP limit is answered by hosting the server rather than the laptop —
which is what `deploy/modal/mcp_stub.py` is.

Say that plainly if anyone asks why there is a deployed URL *and* a local path.
Then point out that the deployed URL is the one you can hand to someone who was
not in the room.
