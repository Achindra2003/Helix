# Demoing Helix — the three rooms, exhaustively

A performance script for showing Helix on a local machine, feature by feature,
until nothing is left unshown.

`docs/SCENARIOS.md` grades every module against three rooms — a general team, a
dev team, a research group — and `frontend/app/e2e/rooms.mjs` proves all three
journeys pass against a real stack. This directory is the third thing: the same
three journeys performed **by hand, in the browser, in front of people**.

## Local or the deployed URL

The deployed instance is **<https://achindra2003--helix-serve.modal.run>**, and
`rooms.mjs` passes all 43 of its assertions against it. Both paths work.

> **Rewritten 13 August 2026, twice.** This section first claimed a free host
> could not run the neural embedder, then that a fatal outage was a database
> problem. Both were wrong and both are recorded in
> [`05-ON-THE-DEPLOYMENT.md`](05-ON-THE-DEPLOYMENT.md), because they are
> mistakes worth not repeating. The truth was the boring one already written in
> the sizing table: ~570 MB of application does not fit a 512 MB box. Moving to
> one with 2 GB fixed it and changed nothing else.

| | Local | Deployed |
|---|---|---|
| Grounding, citations, resurfacing, convergence | yes | **yes** — verified |
| Deep Reasoning to a verdict | yes | **yes** — converged |
| Agent mode, tool calls, the tool ledger | yes | **yes** — verified |
| Registering an account on stage | yes | **yes** — 201 in 29s |
| Uploading a document on stage | yes | **yes** |
| MCP tools, allowlist, approval gate | yes | **yes** — the stub is hosted too |
| Observer role enforcement | yes | **yes** — verified |
| Realtime, two windows, a teammate's tokens | yes | **yes** — verified |
| A paused run surviving a restart | yes | no — no volume, session-scoped |
| An MCP server on *your laptop* | yes | never — host the stub instead |
| The seeded eRisk research workspace | yes | no — upload a paper live |
| Handing someone a link they can open | no | **yes** |

**The one caveat.** A deep run on the deployment is capped at 120 seconds rather
than 300, because the platform severs any HTTP request at 150 and a run that
ends on its own terms (`stop_reason="deadline"`) is better than one cut
mid-stream. Runs converge in around 27 seconds, so this is the tail rather than
the common case — but a deliberately hard question can hit it, and the honest
line if it does is that the run halted on its budget, which is a control the
product is *supposed* to have.

Demo locally when you want to improvise. Demo on the URL when the audience
should be able to follow along, or join.

## The files

Read them in order the first time. After that, `00` is a checklist and the room
files are scripts.

| File | What it is |
|---|---|
| [`00-SETUP.md`](00-SETUP.md) | Pre-flight. Start the stack, the MCP server, two browsers, the accounts. **Do this before anything else.** |
| [`01-GENERAL-TEAM.md`](01-GENERAL-TEAM.md) | Room 1 — diverge, converge, leave with a decision and a reason |
| [`02-DEV-TEAM.md`](02-DEV-TEAM.md) | Room 2 — MCP tools, the approval gate, Review mode, the ADR |
| [`03-RESEARCH-GROUP.md`](03-RESEARCH-GROUP.md) | Room 3 — papers, citations that survive, the supervisor |
| [`04-FEATURE-SWEEP.md`](04-FEATURE-SWEEP.md) | Everything the three rooms don't naturally reach. The small things, one line each. |
| [`05-ON-THE-DEPLOYMENT.md`](05-ON-THE-DEPLOYMENT.md) | The same three rooms on the live URL — what was verified there, what differs, and how to get the dev room working on a hosted instance |

## The shape of a full run

Roughly 45–60 minutes to show everything, or about 12 minutes per room if you
only want the spine.

```
   00 SETUP  ────────────────────────────────────────  15 min, once
       │
       ├─ 01 General team ──── diverge → converge → record       ~12 min
       │      the signature move: Explore ways, four columns
       │
       ├─ 02 Dev team ──────── govern → call → approve → audit   ~15 min
       │      the sharpest 30 seconds in the product: description drift
       │
       └─ 03 Research group ── ground → cite → survive a reload  ~12 min
              the finding SCENARIOS.md called the most important one
                                  │
   04 FEATURE SWEEP  ─────────────┴──────────────────  as long as you like
```

## Three rules that will save the demo

**1. Rehearse on the models you will demo on.** `backend/.env` was corrected on
12 August to `openai/gpt-oss-20b` and `openai/gpt-oss-120b`. The two Llama
models it named before stop serving on free Groq keys on **16 August 2026**. If
a rehearsal recording shows different phrasing than the live run, this is why.

**2. Budget the deep runs.** Groq's free tier is roughly 100k tokens a day and
the 120b deep runs are the hog. `WALKTHROUGH.md`'s rule still holds: **at most
one rehearsal deep run** before the real thing. Everything else — chat,
grounding, agent tool calls, the whole of room 1 — is cheap by comparison.

**3. Two browsers or it isn't a demo.** The single most convincing thing Helix
does is a teammate's tokens arriving in *your* open thread, named, live. That
needs a second browser profile. One window shows a good product; two windows
show what the product is *for*.

## What each room proves, in one line

- **General team** — Helix can hold a disagreement, explore four answers at
  once, and end with a written decision that names what lost.
- **Dev team** — the one part of the system that reaches outside the workspace
  is governed, gated, and auditable afterwards.
- **Research group** — a claim's evidence is attached to the claim, survives a
  reload, and lands in the export.
