# 04 — The exhaustive feature sweep

Everything the three room scripts don't naturally reach, plus everything they do,
as a checklist. Work down it and nothing is left unshown.

Sixteen functional requirements, five ideas, one screen at a time.

---

## If you only have ten minutes

The eight moments that carry the product, ranked. Each is one paragraph of
speech and one gesture.

1. **A teammate's tokens arriving in your open thread**, named, live, without a
   refresh. *(Room 1, beat 2 — two windows)*
2. **Explore ways** — four angles, four real branches, four answers at once.
   *(Room 1, beat 5)*
3. **Reload the page and the citations are still under the claim.** *(Room 3,
   beat 4)*
4. **The MCP description rewrite** — a server changes what the model will be
   told, and Helix un-arms the tool by itself. *(Room 2, beat 7)*
5. **The approval gate stopping a call before it happens** — point at the
   server's log window showing nothing yet. *(Room 2, beat 6)*
6. **Resurfacing** — start typing, and the workspace remembers. *(Room 1, beat
   11)*
7. **Deep Reasoning halting on convergence**, watched and steerable, with a Stop
   button. *(Room 2, beat 9)*
8. **The decision report naming the alternative that lost.** *(Room 1, beat 10)*

---

## 1. Identity, workspaces, roles — FR-1, FR-2, FR-3

- [ ] **Register** in front of them. Fifteen seconds, no setup.
- [ ] **The seeded example workspace** — registration seeds a thread that has
      already been forked, a second conversation referenced from it, a finished
      deep run, and an ingested document. *"Nobody starts at an empty screen —
      and it's static content, so it costs no tokens and needs no key."*
- [ ] **Workspace switcher** — the logo at the top of the rail.
- [ ] **Invite links carry the role** — `TEAM` → *Outstanding invites* → **as
      Collaborator** / **as Observer** → **copy link**. *"You're not inviting a
      person and then assigning a role. You're handing out a role."*
- [ ] **Revoke an invite** — *"the link stops admitting anyone, immediately"*.
- [ ] **Permission Matrix** — `TEAM`, tagged *policy as data*. The whole role
      model as a table, not scattered `if` statements.
- [ ] **See it as** — top bar. Preview the app as Collaborator or Observer
      without logging out.
- [ ] **Remove a member.**
- [ ] **Account settings** — bottom of the rail.
- [ ] **Password reset** exists (no email server locally — say it, don't demo it).
- [ ] **RBAC is server-side on every route.** Worth saying, not clicking:
      identity comes from the JWT and client-supplied ids are ignored; probing a
      workspace you're not a member of returns **404**, so non-membership
      doesn't confirm the workspace exists.

## 2. Conversations, streaming, presence — FR-4, FR-5

- [ ] **Shared vs private threads.** A private thread never appears in anyone
      else's lists, fetches, or realtime room.
- [ ] **Token streaming** over SSE for the asker.
- [ ] **Live fan-out** over the workspace WebSocket for everyone else — the
      attribution banner and author-coloured margins.
- [ ] **Presence that says where, not just who** — the roster shows which
      *branch* each teammate is reading.
- [ ] **Drafting indicator** — teammates can see someone is composing.
- [ ] **Shared context** — have window B ask a follow-up in the same thread and
      show the answer builds on *your* earlier turn. *"For the first time their
      AI work is shared context, not three private monologues."*
- [ ] **Notes** — *"Say this to your teammates instead of to Helix"*. The model
      never reads them.
- [ ] **@mentions** — the picker resolves against the workspace's real members.
- [ ] **Durable notices** — top bar, *What you missed* / *While you were
      elsewhere*, surviving a closed tab. **clear** empties it.
- [ ] **Edit and resend** — hover your own message. Safe only when nothing has
      forked from it; history stays append-only for anyone who branched.
- [ ] **Delete a message and its reply.**
- [ ] **Rename / delete a conversation** — `⋯`.
- [ ] **Search everything** — `FIND` or `Ctrl+K`.

## 3. Branching and deciding — FR-6, FR-13

- [ ] **Fork here** — hover any message. *"A branch is a pointer, not a copy —
      forking writes one row, and history is a walk up `parent_id` that crosses
      fork boundaries. A branch inherits exactly its ancestors' context, and
      siblings stay perfectly isolated."*
- [ ] **Explore several ways at once** — two to six angles, a branch each,
      labelled from the angle itself.
- [ ] **Compare explorations** — reopen the columns later from the lineage.
- [ ] **Approval voting** — back as many as you'd accept; withdrawable.
- [ ] **The tally decides nothing** — adopting still requires a written reason.
      *"The votes are evidence for that reason, never a substitute for it."*
- [ ] **Verdicts** — adopted / abandoned, each with a reason.
- [ ] **Conclude the thread** — *"A reading of the room, not the decision."*
- [ ] **Helix can draft the conclusion** from the branches, and you edit it.
      *"The draft and the record are separate actions, because a draft nobody
      accepted is not a conclusion."*
- [ ] **The decisions ledger** — `MAP`, per workspace.
- [ ] **Replay this thread** — `⋯`, the scrubber. Leave replay with the control
      in the team strip.
- [ ] **Export branch as Markdown / JSON**, authenticated.
- [ ] **Export decision report** — *"deliberately includes the branches that
      were weighed and rejected."*
- [ ] **Link another thread's context** — `⋯`. Live in both threads.
- [ ] **Say what this thread is about** — a PR, an issue, a spec.
- [ ] **The Map** — a zoomable graph: every conversation a spine of turns, forks
      splitting at the exact message they diverged, references drawn as gilt
      threads between threads, **live presence dots** on branches teammates have
      open, click any node to land there. *"One aggregate read, with node
      content stripped out, so a busy workspace still ships a small payload."*

## 4. Memory and grounding — FR-15

- [ ] **Proactive resurfacing** — the "✦ explored before" strip. **≥18
      characters, then pause.** Relevance-gated on measured embedding floors.
- [ ] **Knowledge base upload** — txt · md · code · pdf, up to 8 MB.
- [ ] **Workspace-wide grounding** — chat *and* Deep Reasoning ground
      automatically, with no per-conversation attaching.
- [ ] **Hybrid retrieval.** *"Dense vectors for paraphrase — 'how do we roll back
      a deploy?' finds the runbook that never says 'roll back' — fused by RRF
      with BM25 for the exact rare terms, error codes, env-var names, ticket ids,
      where an embedding carries almost no signal."*
- [ ] **Citations announced before the first token.**
- [ ] **Citations that survive a hard reload**, in both exports and the decision
      report.
- [ ] **Catalogued references** — DOCS → *add ref*: author, year, title,
      DOI/arXiv. One `cite_as` rule shared by the chip, the exports and the
      model's context.
- [ ] **The relevance floor** — no chips on an unrelated question. *"That's the
      floor working, not a bug."*
- [ ] **Knowledge-base search** — the same ranking chat grounding uses.
- [ ] **Delete a document** — and it stops grounding immediately.

## 5. Agent mode — FR-14

- [ ] **Three built-in tools**, with `web_search` **not** allowed by default.
- [ ] **Availability** — web search greys out with no Tavily key.
- [ ] **The owner-governed allowlist** — `SETUP` → Agent tools → **Save tools**.
- [ ] **Enforced by binding, not by refusal** — *"an un-allowed tool is never
      offered to the model at all."* Prove it with `close_pull_request`.
- [ ] **MCP server registration** — `+ Add a server`, **Add and discover**.
- [ ] **Discovery logged live** in the stub's window — `initialize`,
      `tools/list`.
- [ ] **Tools labelled with their source** — `mcp:github`.
- [ ] **Descriptions shown verbatim and in full.** *"Approving a tool means
      approving text the model will obey."*
- [ ] **MCP tools default to sensitive.**
- [ ] **Human-in-the-loop approval** — the run checkpoint-pauses **server-side**
      until a member approves or denies.
- [ ] **Description drift** — `/drift`, then **refresh**. *"A server that
      rewrites a description un-approves it until a human re-reads the new
      text."* Then **I've read this — accept it**.
- [ ] **Remove a server.**
- [ ] **The live tool ledger** in every reply — call, arguments, status —
      **relayed to watchers too**.
- [ ] **Encrypted credentials** — per-workspace, Fernet-encrypted at rest,
      write-only at the HTTP surface, reusing the provider key's machinery.
- [ ] **Agent runs archived** beside deep runs, with their tool transcript.

## 6. Deep Reasoning (Ouroboros) — FR-9, FR-10, FR-11

- [ ] **Six modes**, chosen **per run** — Explore, Analyze, Create, Solve,
      Philosophize, Review. *"The mode is a property of the question, not of the
      workspace."* Recorded in provenance.
- [ ] **It halts because the answer settled** — successive syntheses compared in
      embedding space, stopping on semantic convergence, with a compute budget
      and a wall-clock deadline only as backstops.
- [ ] **The monitor** — topology strip lighting node by node, energy and budget
      meters, depth / loop-guard / stability / confidence / tokens, a live step
      trace.
- [ ] **Guided mode** — pauses between cycles so any Collaborator can inject
      guidance mid-flight.
- [ ] **Steer someone else's run** from window B. The best two-window moment
      after streaming.
- [ ] **Stop** — kills the run server-side.
- [ ] **Runs are durable** — *close the tab mid-run and reopen it*. The run
      executes in a server-side task; SSE responses are subscribers to a run log
      you rejoin from a sequence number.
- [ ] **A paused run survives a backend restart** — locally, because checkpoints
      are on a real disk. **This is a local-only demo**; a free host with an
      ephemeral disk loses it.
- [ ] **Queue indicator** — when the workspace's concurrency cap (2 runs) is hit,
      the rest queue visibly.
- [ ] **Run history drawer** — each past run's model and thresholds.
- [ ] **Crystallized answer** and **Provenance** in the archive.
- [ ] **The claim is measured** — `backend/evals/FINDINGS.md`: the controller
      matched fixed-4-cycle quality at **~half the tokens** and self-terminated
      on `converged` in every run. *"That pilot was on a 70B; today's default is
      gpt-oss-120b, and re-running it is open work — the findings are a record of
      what was tested, not a claim about today's default."* **Say that caveat.**
      It is the most credible sentence in the demo.

## 7. Governance, cost, operations — FR-8, FR-12, FR-16

- [ ] **BYO API key per workspace** — `SETUP` → Provider, tagged *bring your own
      key*. Groq, OpenAI-compatible, or Ollama. Encrypted at rest, never returned
      by any API. *"The server's `.env` stays the fallback, so a self-hoster
      configures nothing and a hosted instance can ship with no fallback key at
      all — a workspace can never spend the operator's."*
- [ ] **Point a workspace at a local Ollama** — unreleased work never leaves the
      building.
- [ ] **Test the provider** from the panel.
- [ ] **Spend** — chat and deep tokens with an estimated cost.
- [ ] **The usage ledger** — `/api/workspaces/{id}/usage`: per-call tokens and
      cost, plus a per-tool breakdown with calls, outcomes, average latency, and
      **who approved what**. *"Tool arguments are hashed, never stored."*
- [ ] **Resilience at the LLM seam** — retry on failures *before the first
      token* (*"a blip, not a reasoning signal"*), a per-endpoint circuit breaker
      so a dead key fails fast, and ordered fallback.
- [ ] **Rate limiting** — auth, messages, runs and uploads each have their own
      window.
- [ ] **`/health`** — reports whether durable runs are actually available.
      Open `http://localhost:8000/health` in a tab.
- [ ] **Opt-in observability** — OTel GenAI spans for every LLM call, reasoning
      cycle, retrieval and tool execution; Sentry when `SENTRY_DSN` is set.
      *"Both are an exact no-op when unset — no SDK, no network client, no
      behaviour change."*
- [ ] **API docs** — `http://localhost:8000/docs`, if the audience is technical.

## 8. The craft layer

Small, and they are what make it read as a product rather than a project.

- [ ] **Light and dark** — the theme toggle. The deck's screenshots are the dark
      variant; `docs/screenshots/` is light.
- [ ] **Responsive** — narrow the window. There is an e2e check for this
      (`responsive.mjs`).
- [ ] **The landing page** at `/` — the public statement piece.
- [ ] **Motion** — the auth tab pill, the picker card springs, the rail's active
      pill.
- [ ] **Empty states with real copy** — *"An unopened volume"*, *"A blank
      page"*, *"The shelf is empty"*.
- [ ] **Prompt library updates live for the room.**
- [ ] **Glyphs used consistently** as state, not decoration.

## 9. Engineering claims worth stating out loud

Not clickable. Say these when someone asks how real it is.

- [ ] **512 backend tests** (verified by collection on 12 August). Hermetic by
      construction: the `stub` provider plus a throwaway SQLite database mean no
      keys and no network are needed to run the whole suite. The pass/skip split
      varies with what's installed locally — the README records 508 passed / 4
      skipped, a recent local run reported 511 / 1. **Run it and quote the number
      you actually see:** `cd backend && python -m pytest -q`.
- [ ] **An adversarial prompt-injection regression corpus** is part of that
      suite.
- [ ] **CI additionally runs against a real `postgres:16`** and applies every
      migration.
- [ ] **15 Alembic migrations, 23 tables, SQLite and Postgres.**
- [ ] **`rooms.mjs`** — all three room journeys pass end to end against a running
      stack, asserting on the artifacts a room leaves with (the export, the
      report, the ledger) rather than the calls that produced them. Offer to run
      it live; it takes a couple of minutes.
- [ ] **One process, one port.** FastAPI serves the API *and* the built React
      bundle with an SPA fallback. *"No separate web server, no CORS in the
      default path, no second deployment to keep in sync."*
- [ ] **Four seams carry the design** — the conversation store, the producer, the
      LLM provider, and the realtime room. *"Everything else is an implementation
      behind one of them."* This is the sentence that answers "is it
      architected or just built".
- [ ] **The published image** — `ghcr.io/achindra2003/helix:v0.9.0-rc1`,
      anonymously pullable, linux/amd64, ~617 MB.
- [ ] **MIT licensed**, with `CONTRIBUTING.md` and `SECURITY.md`.

---

## Run the proof, live

If the audience is technical, this beats any claim you can make:

```
cd frontend/app
node e2e/rooms.mjs
```

It boots an isolated stack on port 8023 with a throwaway database and the stub
provider, then walks all three rooms and prints `all three rooms hold`.

Other scripts in the same directory, all Node built-ins, no `npm install`:

| Script | What it proves |
|---|---|
| `rooms.mjs` | the three room journeys, end to end |
| `smoke.mjs` | the whole golden path through the real UI in a browser |
| `persistence.mjs` | data and tokens survive a restart |
| `citations.mjs` | citations persist and export |
| `convergence.mjs` | deep runs halt on convergence |
| `onboarding.mjs` | the seeded first-run experience |
| `usability.mjs` / `responsive.mjs` | interaction and layout checks |
| `shots.mjs` / `shots-dark.mjs` | regenerate the screenshots |

---

## Two things to say before you're asked

**On the deployment.** *"It's deployed, and the free tiers can't give it enough
memory to keep the embedder resident — which is exactly the half that makes it
interesting. So I'm showing you the real thing on real hardware. The image is
published and anyone can pull it."*

**On what isn't built.** *"Running the same question in two reasoning modes side
by side. The columns and the fan-out would carry it, but three concurrent 120b
recursive runs is the opposite of cheap, disposable divergence — so it's a cost
decision we made and didn't hide."*

A team that can name exactly what it chose not to build reads as more confident
than one that claims everything works.
