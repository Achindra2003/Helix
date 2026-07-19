# Helix — The Whole Project, One Read

**Who this is for:** every team member, before the presentation. Last time the
professor picked a random person and asked a random question from the slides.
This file exists so that never costs us marks again — read it once end-to-end
(~25 minutes), then skim §12 (rapid-fire Q&A) the night before.

**How this fits the other docs:** this is the *breadth* doc — everything, one
level deep. When you want depth on one thing: `HELIX-FEATURE-TRACES.md` (how
each feature executes, file by file), `HELIX-AI-EXPLAINED.md` (how the
reasoning engine thinks), `backend/evals/FINDINGS.md` (the measured evidence),
`BATON-MANSOOR.md` (the infra lane in full). `TEAM-PREP.md` is from the July 4
milestone and is now stale — trust this file where they disagree.

---

## 1. The pitch (say it in 30 seconds)

**Helix is "Git for your team's AI work."** Most teams use AI in private
browser tabs and lose everything: the prompt that worked, the approach that
failed, the thread where the decision actually happened. Helix is a shared
workspace where a team's AI conversations are **branchable** (fork a thread at
any message and explore in parallel), **live** (teammates' replies stream into
your screen token-by-token), and **remembered** — start typing a question and
Helix resurfaces the teammate's thread that already explored it. When a
question is genuinely hard, escalate to **Agent mode** (the model searches
your documents, past threads, or the web before answering, under a governed
tool allowlist) or **Deep Reasoning** (a recursive run the whole team can
watch, steer, and stop, that halts itself when its answer converges).

The one-line identity: **"The AI workspace that remembers what your team
already figured out."**

## 2. Why it exists (the problem)

Teams adopted ChatGPT-style tools individually, not collectively. The market
gap (`MARKET-VALIDATION.md`, July 2026 landscape) is that team AI knowledge is
**siloed, lost, and re-asked**: no shared record, no branching to compare
approaches, no way to ground answers in the team's own documents, and "deep
thinking" modes that are black boxes with no cost control. Helix's answer to
each: shared branchable threads, proactive resurfacing, a workspace knowledge
base with cited answers, and a reasoning mode that is transparent (live
trace), steerable (pause and inject guidance), and cost-disciplined (halts on
convergence, hard budget cap, kill switch).

## 3. Who built what (the lanes)

The project was split into lanes with formal handoff files ("batons"):

- **Product + AI lane (Achindra)** — the engine, the features, the frontend,
  the tests, the evals. **Finished:** all 16 functional requirements
  delivered, 261 backend tests green, browser-level end-to-end smoke passing.
  Lives on branch `ui-standout`.
- **Infra, DB & hardening lane (Mansoor)** — the production install, security
  hardening, schema migrations, and the hosted instance. **In progress:** P1
  (the one-command production container) landed July 19; the remaining plan
  is `BATON-MANSOOR.md` (P2–P5, detailed in §9 below). This lane is what
  turns "finished product" into "something strangers can run, trust, and
  host."
- **UI/UX direction (Rajnish)** — the design language: light parchment,
  scholarly-manuscript look, oxblood primary buttons, gilt outlines, the helix
  motif; role legible at a glance; deliberately free of occult symbolism.
  Handoff record: `BATON-RAJNISH.md`.

Interfaces between lanes are written contracts (`AI-LANE-CONTRACTS.md`), so
lanes could proceed without blocking each other.

## 4. The stack, in plain English

| Layer | Technology | Why |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite | The real UI at `frontend/app/`; builds clean, typechecked. |
| Backend | FastAPI (Python, async) | All routes under `backend/api/`. |
| Database | SQLAlchemy async; **SQLite** for dev/self-host, **Postgres-ready** (`DATABASE_URL` swap, no code change) | Zero-infra install is a deliberate feature. |
| Streaming to the author | **SSE** (Server-Sent Events) | The model's reply streams token-by-token over one HTTP response. |
| Real-time to the room | **WebSocket** room per workspace | Presence, live fan-out of teammates' turns, live deep-run traces. |
| Auth | JWT + bcrypt | Identity comes from the token on every route; client-sent IDs are ignored. |
| LLM providers | Groq (hosted) / Ollama (local) / stub (tests) behind one interface | Chat uses a fast small model; Deep Reasoning uses its own 70B (`llama-3.3-70b-versatile`). |
| Agent & Deep Reasoning | LangGraph (graph-based agent runtime) | Tool loop with checkpoint-pause for human approval; the vendored Ouroboros engine under `backend/engine/`. |
| Embeddings | `all-MiniLM-L6-v2` via sentence-transformers, local | Powers convergence detection, resurfacing, workspace search, and RAG. Pure-Python lexical fallback if the neural deps aren't installed. |

**The one architectural idea to know:** every way of producing a reply — plain
chat, agent run, deep run — goes through the same spine (`engine.send` with
swappable *producers*). That's why streaming, persistence, fan-out, grounding,
and telemetry work identically for all of them: they're implemented once.

## 5. Every feature, one paragraph each

All 16 functional requirements are delivered (`REQUIREMENTS-COVERAGE.md` maps
each to the SRS). Grouped the way they're really built:

**Auth & accounts (FR-1).** Register/login with bcrypt-hashed passwords;
a JWT identifies you on every subsequent call; change-password and
delete-account flows exist. The token persists across reload.

**Workspaces, invites, roles (FR-2, FR-3).** A workspace is the tenancy
boundary — everything (threads, prompts, documents, settings) is scoped to
one. Invite links carry a role and an expiry. Three roles: **owner ⊃
collaborator ⊃ observer**. RBAC is enforced **server-side on every route**
(the UI mirrors it, but the API is the wall): reads need membership, writes
need collaborator+, observers are read-only *at the API*. A non-member
probing someone else's workspace gets **404, not 403** — so outsiders can't
even confirm a resource exists.

**Conversations & streaming (FR-4).** Threads are **shared** or **private**
(private = author-only; never appears in others' lists, fetches, or the
realtime room). Replies stream token-by-token over SSE. The conversation is
an **immutable node tree** — messages are never edited in place, which is
what makes forking, replay, and embedding-once all safe.

**Real-time multiplayer (FR-5).** One WebSocket room per workspace: a live
presence bar (including *which branch* each teammate is reading), teammates'
turns streaming into your open thread with an attribution banner, new
threads/forks/prompts appearing without refresh. Single-process rooms by
design; the Redis seam exists if multi-instance ever matters.

**Fork & branch tree (FR-6).** Fork any message into a new branch that
inherits all ancestor context. **Fork is O(1)** — it creates a branch record
pointing at the fork node; nothing is copied, because the node tree is
immutable and shared. Sibling branches stay isolated. The lineage sidebar and
the **Map** (the workspace as a zoomable graph — spines of turns, forks
splitting at the exact divergence message, references as threads between
conversations, live presence dots) visualize it.

**Prompt library (FR-7).** Save/tag/search prompts; **Insert** runs one as a
turn. Saves appear live for the whole room.

**Provider abstraction & BYO keys (FR-8, FR-16).** Providers sit behind one
interface (groq/ollama/stub). Each workspace can plug in **its own** API key
(owner-only panel, key **encrypted at rest** — Fernet, key derived from the
server's JWT secret), pick models, test the connection. Server `.env` values
are the fallback for self-hosters; a hosted instance ships with *no* fallback
key, so a workspace can never spend the operator's money. Every LLM call is
wrapped in retry + circuit-breaker + safe-fallback.

**Deep Reasoning (FR-9–FR-12, one path).** The composer's ⟳ button starts a
recursive **reason → reflect → synthesize** loop on the 70B model that halts
when the answer **converges** (successive syntheses become semantically
stable, measured with MiniLM embeddings) or hits the compute budget. The
run executes **server-side**: closing the tab doesn't kill it; reload
reconnects. The monitor shows the trace live — topology strip, energy/budget
meters, a stability sparkline climbing to the halting threshold — and
teammates on the same shared branch see it too. **Kill** stops it
server-side; **guided mode** pauses between cycles so anyone can inject
steering; runs are queued per workspace and archived with provenance (which
model/thresholds produced them).

**File grounding / knowledge base (FR-15).** Upload documents to a workspace
(8 MB cap, extension allowlist); they're chunked and embedded server-side.
Chat *and* deep replies automatically ground on relevant chunks **with
citation chips** — but only when relevance clears a measured floor, so
grounding is silently absent on unrelated questions (that's the gate working,
not a bug). Only extracted text is kept — no blob store, by design.

**Agent mode (FR-14).** The ⚒ button lets the model *search before it
speaks*: the knowledge base, past conversations, or the web. Three policy
layers, enforced **by binding, not refusal** — un-allowed tools are never
even offered to the model: (1) a catalog with availability (web search greys
out without a Tavily key), (2) an owner-governed allowlist, (3)
**human-in-the-loop approval** — a sensitive call checkpoint-pauses the run
until a member approves or denies. Every reply carries a tool ledger (call,
args, status), relayed to watchers live.

**Proactive resurfacing (§11 of the traces — the identity feature).** Every
message is embedded when written (fire-and-forget, retried, backfilled on
read). While you type, after 18+ characters and a 700 ms debounce, the draft
is embedded and cosine-compared against every node you're *allowed to see*
(the SQL join carries the same visibility clause as thread listing — private
threads can never resurface for a non-author). Matches above a floor render
as "✦ explored before" chips over the composer; click one to jump to that
thread. The client floor (0.33) is stricter than the server's (0.15) because
this surface is unsolicited — a wrong chip is noise. The same endpoint powers
workspace search *and* the agent's search-conversations tool, so the agent
inherits the visibility guarantees for free. No vector DB: vectors are packed
float32 in an ordinary column; cosine runs in Python — fine to ~10⁵ nodes,
with pgvector as the labeled escape hatch beyond that.

**Replay & export (FR-13) and telemetry.** A replay scrubber steps through
any thread; export to Markdown/JSON is an authenticated download. Every LLM
call is logged (`LlmCallRow`) with a per-workspace `/usage` endpoint.

## 6. How the reasoning engine thinks (Ouroboros, short version)

Deep Reasoning is a vendored engine (`backend/engine/`) built on LangGraph.
Each cycle: **reason** (generate an answer), **reflect** (critique it),
**synthesize** (revise). After each cycle it embeds the synthesis and compares
it with the previous one; when the answer stops moving — semantic stability
plus confidence over threshold — it declares **convergence** and halts. Three
other stops exist: the compute-budget cap, a wall-clock deadline per segment,
and the human kill switch. Guided mode inserts a pause between cycles where a
human can inject direction. Full internals: `HELIX-AI-EXPLAINED.md`.

## 7. The evidence — how we know it works

Three verification levels, all green on `ui-standout`:

1. **261 hermetic backend tests** — no network, no keys, no Docker (stub
   provider + throwaway SQLite). Cover RBAC gating, WS rooms, guided steer,
   provider resilience, durable runs, grounding, the agent loop's approval
   gate and allowlist, and an **adversarial injection-regression corpus**.
2. **Browser end-to-end smoke** (`frontend/app/e2e/smoke.mjs`) — spawns its
   own backend + frontend and drives a real browser through the 10-step
   golden path: register → workspace → streamed chat → upload → cited
   grounding → resurfacing → agent run → deep run → map. Its screenshots are
   the ones in the README.
3. **A scripted 2-user live e2e** (real HTTP + WS + Groq), 15/15 checks.

## 8. The eval — Deep Reasoning's measured claim (know this cold)

We didn't assert Deep Reasoning is better; we **measured** it, twice
(`backend/evals/FINDINGS.md`). Three arms per question: **fixed-1** (single
pass), **fixed-4** (always 4 cycles — the naive "think longer" design), and
**adaptive** (our convergence controller). Same 70B engine, blind judge,
0–10 rubric.

**Hard-set results (8 questions engineered so single-pass should fail; full
8/8 coverage as of July 17):**

| arm | mean score | mean tokens | stop reason |
|---|---|---|---|
| fixed-1 | **8.75** | **1,729** | budget ×8 |
| adaptive (ours) | 8.63 | 3,774 | **converged ×8** |
| fixed-4 | 8.13 | 7,852 | budget ×8 |

The three sentences to remember:

1. **The controller mechanically works** — all runs self-halted on genuine
   convergence, never the cap, averaging 2 cycles under a budget of 6.
2. **Adaptive beats fixed iteration outright**: better quality than fixed-4
   at **~half its tokens**. On the hard set, blind iteration didn't just cost
   more — it scored *worst* (over-iteration dilutes good answers).
3. **Single-pass was not beaten on average** — fixed-1 leads by 0.13, inside
   noise. So the honest pitch is **transparency, steerability, and
   disciplined cost — not higher IQ.** Adaptive's two outright wins were both
   the designed class — questions with **interacting constraints** (a
   scheduling problem, a conflicting-specs API question) where the reflect
   pass catches a violated constraint. Those are the demo questions.

Honest caveats we volunteer before anyone asks: small n (8/arm, no error
bars), judge is the same model family as the engine, absolute rubric
compresses scores. Saying this out loud is deliberate — a measured, narrow,
defensible claim is the credibility feature no competitor demo has.

## 9. Mansoor's lane — install, hardening, migrations, hosting

**Status: P1 shipped July 19 (commit `8d691bc`); P2 is next and completes
the launch threshold. The full plan is `BATON-MANSOOR.md` (July 17).**

What already exists on his side of the fence (don't double-claim): JWT auth,
server-side RBAC, invite expiry, the async DB layer with the
SQLite→Postgres swap, a boot-time schema shim, dev-mode Docker files, and the
in-process realtime rooms.

The four work packages, in priority order:

- **P1 — the production container (✅ landed July 19).** Multi-stage
  Dockerfile that builds the frontend and serves it from FastAPI on one port;
  non-root user; healthcheck; SQLite on a named volume by default, a separate
  compose file for Postgres. A clean machine goes from `git clone` to a
  registered user with **one command**. Making a clean install work also
  surfaced and fixed real defects: the Postgres URL lacked the async driver
  (`postgresql+asyncpg://`) so that path could never have booted, a pinned
  `pydantic-settings` was silently unsatisfiable next to the engine deps, and
  on Linux torch pulled ~4.5 GB of unusable CUDA libraries (now the CPU
  build — 2.5 GB image instead of ~7 GB). Still open from the P1 spec: the
  GitHub Actions CI + GHCR publish, and the "slim image" build option
  (deep-reasoning deps excluded) that the free-tier VM's 1 GB RAM needs —
  with the known tradeoff that slim degrades resurfacing to the lexical
  fallback embedder.
- **P2 — secure-by-default.** Refuse to boot with the dev JWT secret (unless
  explicitly in dev mode); rate limits on signup and the message/deep/agent
  routes; modest caps (workspaces per user, members, message length, invite
  max-uses). The threat model is DB spam and floods, **not token theft** —
  BYO keys mean a hosted Helix never holds a key worth stealing beyond each
  workspace's own encrypted one.
- **P3 — Alembic migrations.** A proper schema baseline over the six model
  files. Posture: self-hosters keep zero-infra boot-time table creation; the
  hosted instance runs real migrations.
- **P4 — hosted-instance kit (Track B).** Postgres + nightly backups,
  password reset (transactional email), monitoring (Sentry + uptime checks),
  and a **seeded example workspace** per new user so resurfacing, the Map,
  replay, and grounding all demo without anyone pasting a key.
- **P5 — labeled stretch seams (not blockers):** a blob store for original
  files, restart-surviving runs (today a run paused for approval dies with a
  server restart), Redis fan-out for multi-instance realtime.

## 10. Hosting: the GCP decision (decided July 18)

Track B will run at **$0 on GCP's Always Free tier** — but on the **one free
e2-micro VM running the P1 compose file**, *not* Cloud Run. Why Cloud Run was
rejected: its headline feature (scale-to-zero) is exactly wrong for Helix,
which keeps live state in-process (WS rooms, paused runs) — every idle-out is
a restart; WebSockets hold Cloud Run instances open so the real budget
(instance-seconds, ~100 free hours/month) burns while users just have tabs
open; and requests are severed at 60 minutes. The always-on free VM is what
Helix's single-instance design wants anyway. Order of operations: Mansoor
finishes P1+P2 first; then that exact compose file deploys to the VM
(us-west1/us-central1/us-east1, Caddy for HTTPS, $1 budget alert).

## 11. Branches, history, and what's still open

- **`ui-standout`** — the release branch; everything current lives here.
- **`main`** — was frozen at the 25% presentation version until July 19,
  when PR #2 merged `ui-standout` into it; it now tracks the release. Still:
  build on `ui-standout`, not directly on `main`.
- **`v2-complete`** — the earlier finished v2 (kept as a milestone record).
- Git history was **rewritten on July 16** (attribution trailers stripped,
  every hash changed). Anyone with an old clone must `git fetch` +
  `git reset --hard origin/<branch>` — **never `git pull`**, which would
  merge the old history back.

Open items: Mansoor's P2–P4 (P1 landed July 19); and three human items — the
**license file** (the one legal blocker for open-source launch), the **demo
GIF**, and the first **real users**.

## 12. Rapid-fire Q&A — the questions a professor actually asks

**Q: What is Helix in one sentence?**
A shared, branchable AI workspace for teams — "Git for your team's AI work" —
that remembers what the team already figured out.

**Q: How is a fork O(1)? Doesn't it copy the conversation?**
No — messages live in an immutable node tree. A fork creates a branch record
pointing at the fork-point node. Ancestors are shared by reference; nothing
is copied.

**Q: How do you stop one workspace from seeing another's data?**
Every route derives identity from the JWT and checks workspace membership
server-side before touching data; every list/search query carries the
visibility clause in SQL. Probing a workspace you're not in returns 404, so
you can't even confirm it exists.

**Q: Why 404 instead of 403 for non-members?**
403 confirms the resource exists; 404 leaks nothing. It's an
information-disclosure defense.

**Q: How does Deep Reasoning know when to stop?**
It embeds each cycle's synthesis and measures semantic stability against the
previous one; when the answer stops moving and confidence clears the
threshold, it halts as "converged." Backstops: a compute-budget cap, a
wall-clock deadline, and a human kill switch.

**Q: Did you prove Deep Reasoning gives better answers?**
We measured it honestly, and no — not on average. What we proved: the
controller matches-or-beats always-4-cycles quality at about half the
tokens, converging by itself every time, and it wins outright on
interacting-constraint questions where a verification pass catches a violated
constraint. The pitch is transparency, steerability, and disciplined cost —
not higher IQ. (Full numbers: §8.)

**Q: Why is there no vector database for the embeddings/RAG?**
Deliberate simplicity: vectors are packed float32 in an ordinary column and
cosine runs in Python — microseconds at our scale, identical on SQLite and
Postgres, zero extra infra. The documented ceiling is ~10⁵ candidates; past
that the labeled escape hatch is pgvector.

**Q: How does resurfacing avoid showing me someone's private thread?**
The similarity search is one SQL join that carries the exact same visibility
clause as thread listing — private threads are filtered in the query itself,
not after.

**Q: What stops the AI agent from calling a tool it shouldn't?**
Policy by **binding, not refusal**: tools outside the owner's allowlist are
never bound into the model's tool set at all — it can't call what it's never
offered. Sensitive calls additionally checkpoint-pause for human approval.

**Q: Where are API keys stored? What if the server is breached?**
Per-workspace keys are encrypted at rest (Fernet; key derived from the server
JWT secret). Rotating the JWT secret invalidates stored keys by design — the
failure mode is "re-paste your key," never a leak. A hosted instance carries
no fallback key, so there's no master key to steal.

**Q: Why both SSE and WebSockets?**
SSE streams the model's reply to its author over a plain HTTP response —
simplest possible unidirectional stream. The WebSocket room handles
everything multiplayer: presence, fan-out of teammates' turns, live run
traces. Right tool per direction.

**Q: What happens if I close the tab during a deep run?**
Nothing bad — runs execute server-side. Reload and the monitor reconnects.
The known limit (a P5 item): a server *restart* kills in-flight runs.

**Q: Why SQLite? Isn't that a toy?**
It's the self-host feature: `docker compose up` with zero infra. The DB layer
is async SQLAlchemy behind a store interface tested against both engines;
switching to Postgres is one env var, no code change.

**Q: What's your test strategy?**
Three levels: 261 hermetic backend tests (stub LLM, throwaway SQLite, no
network — run anywhere, including CI with no secrets), a browser-level
10-step e2e smoke driving the real UI, and a scripted 2-user live e2e over
real HTTP + WS + Groq.

**Q: What's NOT done? (answer honestly)**
Security hardening (Mansoor's P2 — next up; P1's install shipped July 19),
Alembic migrations and the hosted kit (P3–P4), the license file, the demo
GIF, and real users. Known deferrals, on purpose: Postgres RLS, Redis multi-instance
fan-out, blob storage for original files, restart-surviving runs.

**Q: What's the business/launch model?**
Open source, two tracks. Track A: the repo *is* the product — self-host with
one command. Track B: a free hosted demo where each workspace brings its own
LLM key, so operating cost is one small VM (the free GCP e2-micro) and the
threat model is ordinary web hygiene, not token theft.

**Q: Who did what?**
Product + AI lane (features, engine, frontend, tests, evals): Achindra —
complete. Infra lane (install, hardening, migrations, hosting): Mansoor —
P1 (production container) shipped; P2–P4 remain. UI/UX direction and design
system: Rajnish.
Lanes hand off through written contract docs, like real teams do.

## 13. Reading map (if you want to go deeper)

1. `README.md` — the public face: identity, screenshots, status.
2. `HELIX-FEATURE-TRACES.md` — every feature's execution path through the
   real code, written for a newcomer. The best second read.
3. `HELIX-AI-EXPLAINED.md` — the reasoning engine's internals.
4. `backend/evals/FINDINGS.md` — the full eval method, numbers, and caveats.
5. `REQUIREMENTS-COVERAGE.md` — all 16 FRs + NFRs mapped to the SRS.
6. `BATON-MANSOOR.md` — the infra lane's complete work plan.
7. `LAUNCH-PLAN.md` / `MARKET-VALIDATION.md` — why the product exists and
   how it ships.
