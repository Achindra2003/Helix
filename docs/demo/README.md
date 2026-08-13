# Demoing Helix — the three rooms, exhaustively

A performance script for showing Helix on a local machine, feature by feature,
until nothing is left unshown.

`docs/SCENARIOS.md` grades every module against three rooms — a general team, a
dev team, a research group — and `frontend/app/e2e/rooms.mjs` proves all three
journeys pass against a real stack. This directory is the third thing: the same
three journeys performed **by hand, in the browser, in front of people**.

## Local or the deployed URL

> **Corrected 13 August 2026.** This section used to say a free host could not
> run the neural embedder at all. Half of that was wrong and half was right, and
> it is worth keeping both halves straight. **Wrong:** MiniLM is resident on
> <https://helix-eqyu.onrender.com> and answering — grounding, citations and
> convergence are all real there, measured rather than assumed. **Right:** the
> box is too small. The application is ~570 MB resident and Render's free tier
> is 512 MB with no swap, and it has been OOM-killed in practice. See
> [`05-ON-THE-DEPLOYMENT.md`](05-ON-THE-DEPLOYMENT.md) for the evidence, the
> deployed-instance script, and the hosting options.

Both paths work. What separates them is headroom, not features:

| | Local | Deployed |
|---|---|---|
| Grounding, citations, resurfacing, convergence | yes | **yes** — verified |
| Realtime, two windows, steering a teammate's run | yes | **yes** — verified |
| Deep Reasoning to a verdict | yes | **yes** — 22 steps, converged |
| Agent mode, tool calls, the tool ledger | yes | **yes** — verified |
| **Registering an account on stage** | yes | **no** — the memory spike that kills a 512 MB instance |
| **Uploading a document on stage** | yes | **no** — same spike |
| A paused run surviving a restart | yes | no — ephemeral disk, session-scoped |
| An MCP server on *your laptop* | yes | never — host the stub instead |
| The seeded eRisk research workspace | yes | no — prepare your own the day before |
| Handing someone a link they can open | no | **yes** |

The deployed instance is fine to *use* and fragile to *fill*. Registration and
upload both embed a batch, and a batch on top of a resident MiniLM is what puts
a 512 MB container over its limit. Prepare accounts and documents a day ahead
and the live demo never touches that path.

Demo locally when you want to improvise. Demo on the URL when the audience
should be able to follow along, or join — and if the URL needs to be dependable
rather than rehearsed, move it to the 1 GB instance `docs/DEPLOY-RUNBOOK.md`
was written for.

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
