# Helix

**The AI workspace that remembers what your team already figured out.**

Most teams run AI in private tabs and lose everything: the prompt that worked,
the approach that didn't, the thread where the decision actually happened.
Helix is "Git for your team's AI work" — shared, **branchable** conversations
where the record compounds: start typing a question and Helix resurfaces the
teammate's thread that already explored it; answers ground on your own
documents with citations; every fork, run, and source stays visible to the
whole room, live.

And when a question is genuinely hard, escalate it — **⚒ Agent** (the model
searches your knowledge base, past threads, or the web before answering,
under an owner-governed tool allowlist with human approval for anything that
leaves the workspace) or **⟳ Deep Reasoning** (a recursive run the whole team
can watch, steer, and stop, that halts itself when its answer converges).
Never a black box: you see the reasoning, the sources, the tool calls, the
cost, and the moment it decided to stop.

## See it

*The moment Helix exists for — you start typing, and the workspace remembers:*

![Proactive resurfacing: typing a question surfaces the teammate's thread that already explored it](docs/screenshots/03-resurfacing.png)

*An Agent reply: the tool ledger shows what it looked up, the answer cites the workspace's own spec:*

![Agent mode: tool ledger and cited grounding in one reply](docs/screenshots/04-agent-ledger.png)

*Deep Reasoning under supervision — live trace, meters, and a Stop button:*

![The Deep Reasoning monitor mid-run](docs/screenshots/06-deep-monitor.png)

More in [`docs/screenshots/`](docs/screenshots/) — all captured by the automated
click-through (`frontend/app/e2e/smoke.mjs`), which drives the real UI through
the whole golden path (register → workspace → streamed chat → knowledge-base
upload → cited grounding → resurfacing → agent run → deep run → map) as a
browser-level smoke test.

## What Helix does

All 16 functional requirements are delivered and tested. They group into five
ideas.

### 1. A record the whole team is inside

- **Workspaces and roles.** Register, create a workspace, invite people with
  invite links that carry the role they'll get. Three roles: **Owner** (governs
  provider keys and the tool allowlist), **Collaborator** (everything a thread
  needs), **Observer** — who has exactly *one* write, a team note that never
  enters the model's context. An observer can address the room without being
  able to address Helix, spend the key, or alter a thread's lineage.
- **Shared and private threads.** A shared thread belongs to the workspace; a
  private one never appears in anyone else's lists, fetches, or realtime room.
- **Real token streaming**, over SSE for the person who asked and over the
  workspace's WebSocket room for everyone else — so a teammate's reply arrives
  in your open thread **token by token**, named in a live attribution banner
  with author-coloured margins. You can watch a teammate's Deep Reasoning
  trace the same way.
- **Presence that says where, not just who.** The roster shows which *branch*
  each teammate is reading.
- **@mentions with a durable inbox.** `@priya` in a note resolves against the
  workspace's own members and leaves a notice that outlives the tab.
- **Workspace search** across conversations, plus **cross-conversation
  references** — link a thread to another and the link is live in both.

### 2. Branching, and deciding

This is the half that makes it "Git for your team's AI work" rather than a
group chat with a model in it.

- **Fork anywhere, for free.** Hover any message → *fork here*. A branch is a
  *pointer*, not a copy: forking writes one row (O(1)), and history is a walk
  up `parent_id` that crosses fork boundaries. So a branch inherits exactly its
  ancestors' context, and siblings stay perfectly isolated.
- **Explore several ways at once.** Diverging used to cost a dialog and a
  naming decision per branch, which priced "let's try four things" like "let's
  commit to one". Name two to six angles and Helix opens a branch for each,
  labelled from the angle itself.
- **Converge with evidence.** Approval voting on branches — back as many as
  you'd accept, since the real signal in a design argument is usually "either
  of these works" rather than a ranking. **The tally decides nothing.** Adopting
  a branch still requires a member to write down why; the votes are evidence
  for that reason, never a substitute for it.
- **Conclude the thread.** Record what was decided, or have Helix draft it from
  the branches and edit the draft. A draft nobody accepted is not a conclusion,
  so the draft and the record are separate actions.
- **The decision ledger** collects those conclusions per workspace.
- **Replay and export.** Step through a thread with the replay scrubber;
  export authenticated Markdown or JSON; or generate a **decision report** —
  which deliberately includes the branches that were weighed and *rejected*,
  because half of why a decision holds is the alternative that lost.
- **The Map** — the workspace's reasoning as a zoomable graph: every
  conversation a spine of turns, forks splitting at the exact message they
  diverged, references drawn as gilt threads between threads, live presence
  dots on the branches teammates have open. Click any node to land there. It's
  one aggregate read, and node content is stripped out of it, so a busy
  workspace still ships a small payload.

### 3. Memory and grounding

- **Proactive resurfacing.** Start typing a question and threads the workspace
  already explored appear above the composer ("✦ explored before"),
  relevance-gated on measured embedding floors so it stays silent unless it is
  actually the same question. Nobody re-asks what a colleague solved.
- **Knowledge base (file grounding / RAG).** Upload documents to a workspace →
  chunked and embedded server-side → chat **and** Deep Reasoning ground on the
  relevant chunks automatically, workspace-wide, with no per-conversation
  attaching. Retrieval is **hybrid**: dense vectors for paraphrase ("how do we
  roll back a deploy?" finds the runbook that never says "roll back") fused by
  RRF with BM25 for the exact rare terms — error codes, env-var names, ticket
  ids — where an embedding carries almost no signal.
- **Citations that survive.** Sources are announced *before* the first token
  and written onto the persisted node, so the chips are still there after a
  hard reload, in both exports, and in the decision report. On an unrelated
  question there are no chips at all — that's the relevance floor working, not
  a bug.
- **Catalogued references.** DOCS → *add ref*: author, year, title, DOI/arXiv.
  Citations then read as references rather than filenames — in the chip, in the
  exports, and in the model's own context.

### 4. Escalation: Agent mode and Deep Reasoning

Both are the *same* streamed, persisted, budget-accounted turn as an ordinary
message — one mount, three producers. That's why they inherit context,
streaming, fan-out and export without special cases.

**⚒ Agent** — the model searches before it speaks: the knowledge base, past
conversations, or the web. Three policy layers, enforced **by binding rather
than by refusal**, so an un-allowed tool is never offered to the model at all:

1. a catalog with availability (web search greys out with no Tavily key),
2. an **owner-governed allowlist** (SETUP → Agent tools),
3. **human-in-the-loop approval** — a sensitive call checkpoint-pauses the run
   server-side until a member approves or denies from the banner.

Every reply carries a live **tool ledger** — call, arguments, status — relayed
to watchers too. **MCP tool servers** plug into the same catalog: point a
workspace at a server, read each discovered tool's description *verbatim*, then
allow them individually. Discovered tools are approval-gated by default, and a
server that rewrites a tool's description un-approves it until a human re-reads
the new text.

**⟳ Deep Reasoning (Ouroboros)** — a recursive reason → reflect → synthesize
run the whole team can watch, steer, and stop.

- **It halts because the answer settled**, not because a counter ran out:
  successive syntheses are compared in embedding space and the run stops on
  semantic convergence, with a compute budget and a wall-clock deadline as
  backstops.
- **Six modes** — Explore, Analyze, Create, Solve, Philosophize, Review — each
  with its own depth, energy curve and steer interval, chosen **per run**,
  because the mode is a property of the question rather than of the workspace.
  Recorded in the run's provenance.
- **Guided mode** pauses between cycles so any Collaborator can inject guidance
  mid-flight, and **Stop** kills the run server-side.
- **The monitor** shows convergence happening: topology strip lighting node by
  node, energy and budget meters, depth / loop-guard / stability / confidence /
  tokens, a live step trace, a queue indicator when the workspace's concurrency
  cap is hit, and a Run history drawer with each past run's model and
  thresholds.
- **Runs are durable.** They execute in a server-side task, so closing the tab
  doesn't kill one; SSE responses are subscribers to a run log you can rejoin
  from a sequence number.
- **The claim is measured, not vibes** (`backend/evals/FINDINGS.md`): the
  controller matched fixed-4-cycle quality at **~half the tokens**, and
  self-terminated on `converged` in every run rather than hitting the cap. That
  pilot was run on a 70B; the current default deep model is
  `openai/gpt-oss-120b`, and re-running the evaluation on it is open work — the
  findings are a record of what was tested, not a claim about today's default.

### 5. Governance, cost and operations

- **RBAC server-side on every route.** Identity comes from the JWT and
  client-supplied ids are ignored; reads need membership, writes need
  Collaborator or better, private threads are author-only, and probing a
  workspace you're not in reads as **404** — non-membership doesn't confirm
  existence.
- **BYO API key per workspace.** Each workspace can plug in its own Groq or
  OpenAI-compatible key and model names, encrypted at rest and never returned
  by any API. The server's `.env` stays the fallback, so a self-hoster
  configures nothing new and a hosted instance can ship with no fallback key
  at all — a workspace can never spend the operator's.
- **Resilience at the LLM seam** — retry on failures that happen *before the
  first token* (a blip, not a reasoning signal), a per-endpoint circuit breaker
  so a dead key fails fast, and ordered fallback.
- **A usage ledger.** Durable per-call token and cost accounting at
  `/api/workspaces/{id}/usage`, with a per-tool breakdown: calls, outcomes,
  average latency, and who approved what. Tool arguments are hashed, never
  stored.
- **Opt-in observability.** OpenTelemetry GenAI spans for every LLM call,
  reasoning cycle, retrieval and tool execution — point
  `OTEL_EXPORTER_OTLP_ENDPOINT` at Langfuse, Jaeger or any collector. Sentry
  when `SENTRY_DSN` is set. Both are an exact no-op when unset: no SDK, no
  network client, no behaviour change.
- **Nobody starts at an empty screen.** Registration seeds an example
  workspace with a thread that has already been forked, a second conversation
  referenced from it, a finished deep run, and an ingested document — static
  content, so it costs no tokens and needs no key.
- **Prompt library** — save, tag, search, insert, updating live for the room.
- **Rate limiting**, password reset, and a `/health` endpoint that reports
  whether durable runs are actually available.

## Architecture

One Python process on one port: FastAPI serves the API *and* the built React
bundle, with an SPA fallback. No separate web server, no CORS setup in the
default path, no second deployment to keep in sync.

```
frontend/app/          React 18 + TS + Vite — the real UI
  src/routes/          one file per screen (chat, map, docs, library, panels)
  src/lib/             api · sse · realtime · rbac · theme
  e2e/                 browser-level checks; Node built-ins only, no npm install

backend/api/           FastAPI
  routers/             auth, workspaces/members/invites/settings, notices
  conversation/        the engine — one turn, end to end
    engine.py          send(): persist → history → context → producer → persist
    store.py           the persistence seam; the fork model (branch = pointer)
    producer.py        chat producer + the Producer protocol
    deep_reasoning.py  Ouroboros mapped onto the same event contract
    runs.py resume.py  server-side runs, and paused runs across a restart
    map.py reports.py  the Map's aggregate read; decision reports
  documents/           ingestion + hybrid retrieval (dense + BM25, RRF-fused)
  tools/               agent loop, built-in catalog, MCP, tool telemetry
  providers/           LLM seam: groq | ollama | openai-compatible | stub
                       + resilience, capabilities, pricing
  prompts/             the shared prompt library
  realtime.py          workspace WebSocket rooms (presence + fan-out)
  telemetry.py         OTel GenAI spans + the durable usage ledger
backend/engine/        vendored Ouroboros deep-reasoning engine (LangGraph)
backend/migrations/    15 Alembic migrations; 23 tables; SQLite and Postgres
```

Four seams carry the design — the conversation **store**, the **producer**, the
LLM **provider**, and the **realtime** room — and everything else is an
implementation behind one of them.

**[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) is the full module-by-module
walkthrough**: what each package owns, how a turn flows end to end, the event
contract, the data model, the security posture, and the testing strategy.

## Verification

**512 backend tests — 508 pass, 4 skipped.** Hermetic by
construction: the `stub` provider plus a throwaway SQLite database mean no keys
and no network are needed to run the whole suite, which includes an adversarial
prompt-injection regression corpus.

```bash
cd backend && python -m pytest -q
```

CI additionally runs the suite against a real **postgres:16** and applies every
migration to it on each push. Browser-level checks live in `frontend/app/e2e/`
and need only Node — `smoke.mjs` drives the golden path and captures the
screenshots above; `rooms.mjs` runs three multi-user journeys through the
realtime room; `persistence.mjs` seeds, restarts, and verifies that a token
issued before the restart still works.

## Documentation

| Document | What it's for |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Modules, seams, data model, request lifecycle |
| [`HELIX-USAGE.md`](HELIX-USAGE.md) | Click-by-click: what to do, and what you should see |
| [`HELIX-AI-EXPLAINED.md`](HELIX-AI-EXPLAINED.md) | The AI layer in plain English, layer by layer |
| [`HELIX-FEATURE-TRACES.md`](HELIX-FEATURE-TRACES.md) | Each feature's execution path, with file references |
| [`REQUIREMENTS-COVERAGE.md`](REQUIREMENTS-COVERAGE.md) | Every requirement, its status, and where to see it running |
| [`helix-api-contract.md`](helix-api-contract.md) | The REST, SSE and WebSocket contract |
| [`AI-LANE-CONTRACTS.md`](AI-LANE-CONTRACTS.md) | The AI layer's frozen interfaces |
| [`DESIGN.md`](DESIGN.md) | The visual system — tokens, type, motion |
| [`backend/evals/FINDINGS.md`](backend/evals/FINDINGS.md) | The measured convergence evaluation |
| [`docs/SCENARIOS.md`](docs/SCENARIOS.md) | Every module tested against three kinds of team: holds, bends, or breaks |
| [`MARKET-VALIDATION.md`](MARKET-VALIDATION.md) | The landscape these features were built against |
| [`helix-srs.md`](helix-srs.md) · [`helix-product.md`](helix-product.md) | Requirements, and the product argument |
| [`docs/DEPLOY-HF-SPACES.md`](docs/DEPLOY-HF-SPACES.md) | Deploying a hosted instance |

## Install — one command

```bash
git clone https://github.com/Achindra2003/Helix.git
cd Helix
docker compose up
```

Open **http://localhost:8000**, register, create a workspace, and chat. That
is the whole install — no Python, no Node, no database server, no API key.

The first run **builds** the image rather than downloading one, which takes
roughly ten minutes and wants several GB of free disk (see *About the image*
for where the size goes). Nothing after that first build is slow.

The container serves the API *and* the built UI on one port, stores its data
in a Docker volume (so it survives rebuilds), runs as a non-root user, and
reports health to Docker. It ships on the `stub` provider: a fake model that
echoes back, so every screen is explorable before you decide to plug in a key.

**For real model replies**, either set a key for the whole server:

```bash
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))") \
LLM_PROVIDER=groq GROQ_API_KEY=gsk_... docker compose up
```

…or let each workspace bring its own under **TEAM → Provider** in the UI.

> **Before inviting anyone**, set `JWT_SECRET` to a random value. It signs
> login tokens, and the default is a public placeholder. Changing it later
> logs everyone out and invalidates saved provider keys — their encryption is
> derived from it.

**Postgres instead of SQLite** (for a hosted deployment):

```bash
docker compose -f docker-compose.postgres.yml up
```

### About the image

~2.5 GB, because Deep Reasoning's LangGraph stack and a MiniLM embedding
model are included rather than optional — every feature works on first run,
with nothing to configure. Two deliberate choices behind that number:

- **torch is installed from PyTorch's CPU-only index.** On Linux the default
  wheel pulls the NVIDIA CUDA stack (~4.5 GB of cuBLAS, NCCL, cuSPARSELt)
  that can never execute here — there is no GPU, and torch exists only to run
  a small embedding model. Excluding it is the difference between 2.5 GB and
  roughly 7 GB.
- **The MiniLM weights are baked in at build time**, so the container runs
  fully offline and the first Deep Reasoning request doesn't stall on a
  download.

## Developing without Docker

Dev runs on **SQLite** (a local file, zero infra).

```bash
cp .env.example backend/.env       # runs as-is; SQLite + stub LLM, no keys

# Terminal 1 — backend
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-engine.txt
.venv/bin/python -m uvicorn api.main:app --reload           # http://localhost:8000
# Windows: swap .venv/bin/ for .venv/Scripts/ in both lines above

# Terminal 2 — frontend
cd frontend/app
npm install
npm run dev                    # http://localhost:5173
```

Open http://localhost:5173, register, create a workspace, and chat.
API docs at http://localhost:8000/docs.

**Install both requirements files.** `requirements-engine.txt` is not
optional for development: without it six test modules fail at *collection*
(`ModuleNotFoundError: langchain_core`) and the suite never runs. It also
brings `sentence-transformers`, so convergence and semantic memory use real
MiniLM embeddings instead of the lexical fallback (first run downloads the
model).

### Switch to Postgres later
Set `DATABASE_URL=postgresql+asyncpg://helix:helix@localhost:5432/helix` in
`backend/.env` and start just the database — no code changes:

```bash
docker compose -f docker-compose.postgres.yml up postgres
```

The `postgres` service lives in that file, not the default one; the default
compose file runs Helix alone on SQLite and has no database server in it.

## Choosing an LLM provider

Set `LLM_PROVIDER` in `backend/.env`:

| Value    | Needs                          | Notes                                |
|----------|--------------------------------|--------------------------------------|
| `stub`   | nothing                        | echoes the prompt; default           |
| `groq`   | `GROQ_API_KEY`                 | hosted, fast, free tier              |
| `ollama` | [Ollama](https://ollama.com) running separately, then `ollama pull llama3.2` | local, ~8GB RAM |

A workspace can also choose **`openai_compatible`** in its own Provider panel
— one shape that covers OpenRouter, vLLM, LM Studio, and anything else serving
the OpenAI chat API.

The Groq defaults are `openai/gpt-oss-20b` for chat and `openai/gpt-oss-120b`
for Deep Reasoning. Groq retired `llama-3.3-70b-versatile` and
`llama-3.1-8b-instant` for free and developer-tier keys on 16 August 2026, and
these are its named replacements — both 131k context with tool use and JSON
schema mode.

Helix ships no Ollama container — it points at one you already run, via
`OLLAMA_BASE_URL`. Developing on the host, the default `http://localhost:11434`
is right; from inside the Helix container it is not, because localhost there is
the container: use `http://host.docker.internal:11434`.

Deep Reasoning and agent runs follow the same provider the workspace chats
with — Groq, a local Ollama, or any OpenAI-compatible endpoint — so a fully
self-hosted Helix with no cloud account still gets its flagship feature. They
take their own model (`DEEP_REASONING_MODEL`, or **deep model** in the
Provider panel), so chat can stay on a fast small model while the reasoning
loop gets the strongest one. On Ollama and OpenAI-compatible endpoints the
default is simply the workspace's chat model, since the Groq-shaped default
name would not exist there.

## Restarts

Deep and agent runs pause for a human — a guided run stops for steering, an
agent turn stops for tool approval — and that wait can outlast the server.
**A paused run survives a restart**: its reasoning is checkpointed to
`helix-checkpoints.db` (beside your database; set `CHECKPOINT_PATH` to move
it) and everything around it to a `resumable_runs` row, so steering it after a
deploy picks up where it stopped rather than answering "not found".

A run that is *mid-execution* when the process dies is lost, and costs one
re-run. `GET /health` reports `durable_runs` so you can tell which regime you
are in — it is `false` if the checkpoint driver is missing, in which case the
server still starts and says so in the log.

## Roadmap

Known gaps, stated as gaps rather than as features:

- **Per-conversation model picker.** Today the provider and model are set once
  per workspace, with Deep Reasoning's model as the one independent axis.
- **Postgres row-level security**, as defence in depth behind the per-route
  tenancy checks that enforce it today. The migrations are done — 15 of them,
  and CI applies them to a real Postgres on every push — but table owners
  bypass RLS by default, so this needs a separate non-owner application role
  and a negative test, not just a policy.
- **Redis pub/sub behind the realtime seam** for multi-process deployment. The
  seam is two functions wide; the in-process rooms are correct for the single
  API process this deploys as today.
- **A blob store for original uploaded files.** Only extracted text is kept;
  re-upload re-ingests.
- **Re-running the convergence evaluation** on `openai/gpt-oss-120b`. The
  published findings were measured on a 70B that Groq has since retired for
  free-tier keys.
- **Naming an intermittent test.** The hermetic CI job failed twice on commits
  that touched only documentation and then passed on a third, so one or more
  tests are non-deterministic under CI timing. It doesn't reproduce locally
  (511 pass), and it's worth identifying before v1.0.0.

## Contributing

Issues and pull requests are welcome. [`CONTRIBUTING.md`](CONTRIBUTING.md)
covers how the project is laid out and how to run the tests;
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) is the orientation to read
first; [`SECURITY.md`](SECURITY.md) is how to report a vulnerability privately
rather than in a public issue.

## License

[MIT](LICENSE) — use it, fork it, ship it commercially. Keep the copyright
notice, and understand that it comes with no warranty.
