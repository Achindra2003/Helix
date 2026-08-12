# Helix — architecture and modules

What each part of Helix is, what it owns, and why it is shaped that way. This
is the map you want before reading the source; every section names the real
files so you can go straight to them.

Companion documents: [`HELIX-AI-EXPLAINED.md`](../HELIX-AI-EXPLAINED.md) goes
deeper on the reasoning layer specifically, [`DESIGN.md`](../DESIGN.md) is the
visual system, [`REQUIREMENTS-COVERAGE.md`](../REQUIREMENTS-COVERAGE.md) maps
requirements to where you can see them running, and
[`AI-LANE-CONTRACTS.md`](../AI-LANE-CONTRACTS.md) is the frozen interface list
between layers.

---

## 1. The shape of the whole thing

Helix is **one Python process serving one port**. FastAPI answers the API, and
the same app serves the built React bundle as static files with an SPA
fallback (`api/main.py` — a request that matches no route and no file returns
`index.html`). There is no separate web server, no CORS configuration in the
default path, and no second deployment to keep in sync.

```
                  ┌──────────────────────────────────────────────┐
   browser ─────► │  FastAPI (one port, one process)             │
                  │                                              │
   HTTP  ────────►│  routers ──► engine.send() ──► producer      │
   SSE   ◄────────│                   │              │           │
   WS    ◄───────►│              ConversationStore   ├─ chat     │
                  │                   │              ├─ deep     │
                  │              realtime rooms      └─ agent    │
                  │                   │              │           │
                  │                   ▼              ▼           │
                  │            SQLAlchemy      LLMProvider seam  │
                  │            (SQLite / Postgres)  groq|ollama| │
                  │                                 openai|stub  │
                  └──────────────────────────────────────────────┘
```

Four seams carry the whole design. Everything else is an implementation
behind one of them:

| Seam | Protocol | Implementations | Why it exists |
|---|---|---|---|
| **Store** | `ConversationStore` (`conversation/store.py`) | `InMemoryStore`, SQLAlchemy store | The engine is testable with no database, and SQLite/Postgres is a config change |
| **Producer** | `Producer` (`conversation/producer.py`) | `ChatProducer`, `DeepReasoningProducer`, `AgentProducer` | "One mount, three producers" — chat, deep reasoning and agent runs are the *same* streamed, persisted, budget-accounted turn |
| **Provider** | `LLMProvider` (`providers/base.py`) | `groq`, `ollama`, OpenAI-compatible, `stub` | Swapping models never reaches the engine; the `stub` provider is what makes the test suite hermetic |
| **Realtime** | `broadcast` / `roster` (`realtime.py`) | in-process rooms | Two functions; a Redis pub/sub swap for multi-process would touch this file only |

---

## 2. One turn, end to end

This is the path that matters most. Everything else in the product hangs off
it.

1. **`POST /api/conversations/{branch_id}/messages`** (`conversation/router.py`)
   authenticates the JWT, resolves the branch to its conversation and
   workspace, and checks the caller is a Collaborator or better. Identity
   comes from the token — client-supplied ids are ignored everywhere.
2. **`engine.send()`** (`conversation/engine.py`) persists the user message as
   an immutable node and emits `UserNode`.
3. **`get_history()`** walks `parent_id` from the branch head back to the root,
   *crossing fork boundaries*, so a branch inherits exactly its ancestors and
   nothing from its siblings.
4. **`context.build()`** turns that lineage into a role-structured chat context
   with a system frame that says this is a shared team workspace, not a private
   chat.
5. **Retrieval runs first if it clears its floor.** The knowledge base is
   searched for chunks relevant to this prompt; if the best match beats a
   measured relevance threshold, the chunks are folded into context and the
   producer announces a `Grounding` event *before the first token*, so the UI
   can show sources while the reply is still streaming.
6. **The producer streams.** `ChatProducer` emits `Token`s. `DeepReasoningProducer`
   emits `Step`/`Budget`/`Waiting`/`Complete` plus tokens for the final answer
   only. `AgentProducer` emits `ToolCall`/`ToolResult` and may stop the run
   entirely at an approval interrupt.
7. **The engine persists the assistant node**, writes the grounding sources
   onto it (so a reload still shows the citations), and emits `AssistantNode`
   then `Done`.
8. **Two audiences see it.** The author gets the events over **SSE** on their
   own request. Every other member of the workspace gets the same events
   relayed into the **WebSocket room**, which is why a teammate's turn streams
   token-by-token into your open thread.

If a producer raises mid-stream, the engine catches it, persists whatever
partial reply arrived, and closes with a well-formed terminal
`Complete(status="error")` → `AssistantNode` → `Done`. A client never sees a
torn stream or a 500 in the middle of a response.

### The event contract

One vocabulary, defined once in `conversation/events.py`, serialised to SSE
frames and relayed over the WebSocket unchanged:

`user_node` · `token` · `assistant_node` · `done` · `grounding` · `step` ·
`budget` · `waiting` · `complete` · `deep_run` · `agent_run` · `tool_call` ·
`tool_result` · `queued`

---

## 3. Backend modules

### `api/` — the top level

| Module | What it owns |
|---|---|
| `main.py` | App assembly, router mounting, static SPA serving, lifespan startup (DB, checkpointer, telemetry, monitoring) |
| `config.py` | Every setting, with defaults chosen so a fresh clone runs with no configuration at all |
| `db.py` | Async SQLAlchemy engine and session, SQLite/Postgres portability |
| `models.py` | ORM models. UUID primary keys stored as strings so one schema serves both databases |
| `schemas.py` | Pydantic request/response shapes |
| `security.py` | bcrypt password hashing, JWT issue/decode |
| `deps.py` | The auth and RBAC dependencies every protected route depends on |
| `errors.py` | One error envelope, so clients parse failures the same way everywhere |
| `realtime.py` | The workspace WebSocket room: presence roster + event fan-out |
| `checkpointing.py` | The process-lifetime LangGraph SQLite checkpointer that lets a paused run outlive a restart |
| `reasoning_llm.py` | The LangChain chat client deep and agent runs use, so those paths are provider-agnostic rather than Groq-only |
| `provider_settings.py` | Per-workspace BYO-key resolution; keys encrypted at rest, never returned by any API |
| `mentions.py` | `@name` resolution against workspace members, leaving durable notices |
| `onboarding.py` | The seeded example workspace every new account starts with — static content, costs no tokens, needs no key |
| `telemetry.py` | OpenTelemetry GenAI spans + the durable `llm_calls` usage ledger. Opt-in and env-gated |
| `monitoring.py` | Sentry when `SENTRY_DSN` is set, an exact no-op when it is not |
| `email.py` | Password-reset mail via Resend when configured, a log line when not |
| `rate_limit.py` | A sliding-window limiter in ~30 lines, no dependency |
| `demo_helix.py` | The scripted demo path |

### `api/routers/` — auth and tenancy

`auth.py` (register, login, password reset, account), `workspaces.py`
(workspaces, members, invites with roles, settings, usage, export, MCP
registry), `notices.py` (the mention inbox).

Registration also seeds the example workspace, so the first screen a new
account sees has a forked thread, a referenced conversation, a finished deep
run and an ingested document in it.

### `api/conversation/` — the engine

The largest package, and the one to read first.

| Module | What it owns |
|---|---|
| `engine.py` | `send()` — the one turn, described above |
| `store.py` | The `ConversationStore` protocol and the in-memory reference implementation. **The fork model lives here**: a branch is a *pointer* (`fork_node_id` + `head_node_id`), so forking copies no history — O(1) write, and history is a walk |
| `producer.py` | The `Producer` protocol and `ChatProducer` |
| `deep_reasoning.py` | `DeepReasoningProducer` — maps the Ouroboros LangGraph `astream` onto the event contract |
| `events.py` | The event vocabulary |
| `context.py` | Lineage → role-structured model input |
| `embeddings.py` | Persisted per-node embeddings, versioned by embedder name so an upgrade is a lazy re-embed, not a migration |
| `runs.py` | Server-side background run execution. A dropped connection no longer cancels a three-minute run; SSE responses become subscribers to a per-run log |
| `resume.py` | Paused runs across a restart — the `resumable_runs` record around the checkpoint |
| `run_log.py` | `DeepRunRecorder`: persists each run's trace and provenance, so "yesterday's deep run was weird" is answerable |
| `map.py` | One aggregate read powering the whole Map view — every visible conversation, its branch tree, a content-free node skeleton, and reference edges |
| `reports.py` | The documents that leave Helix: whole-conversation decision reports, including the branches that were weighed and rejected |
| `router.py` | The HTTP surface for all of it |

### `api/documents/` — the knowledge base

`service.py` owns ingestion (extract → chunk → embed) and **hybrid
retrieval**: dense vectors on the shared embedder for paraphrase, plus
`lexical.py`'s Okapi BM25 for exact rare terms (error codes, env-var names,
ticket ids) where an embedding carries almost no signal. The two rankings fuse
by Reciprocal Rank Fusion, and a relevance floor decides whether anything is
injected at all — which is why grounding is silently absent on unrelated
questions rather than citing something irrelevant.

BM25 is ~60 lines here rather than a `rank_bm25` dependency, because workspace
corpora are small enough that the index is not the interesting part.

### `api/tools/` — agent mode

| Module | What it owns |
|---|---|
| `agent.py` | `AgentProducer` — the tool loop as a third producer, with the approval interrupt |
| `builtin.py` | The built-in catalog: search the knowledge base, past conversations, or the web. Every handler returns a bounded string and never raises to the model |
| `mcp.py` | The MCP protocol mapping. `ToolSpec` already *is* MCP's shape — name, description, JSON-schema parameters — so this is a mapping, not a subsystem |
| `mcp_service.py` | The registry, and the rule about what counts as approved |
| `telemetry.py` | Per-tool spans, durable `tool_calls` rows, arguments hashed rather than stored |

Three policy layers, enforced **by binding rather than by refusal** — an
un-allowed tool is never offered to the model at all:

1. **Catalog + availability** — web search greys out with no Tavily key.
2. **Owner allowlist** — SETUP → Agent tools decides what exists for this
   workspace.
3. **Human-in-the-loop approval** — a sensitive call checkpoint-pauses the run
   until a member approves or denies. A discovered MCP tool is approval-gated
   by default, and a server that *rewrites a tool's description* un-approves it
   until a human re-reads the new text.

### `api/providers/` — the LLM seam

`base.py` (the protocol), `groq.py`, `ollama.py`, `stub.py`, and:

- `resilient.py` — retry on transient failures *before the first token* (a blip
  is not a reasoning signal), a per-endpoint circuit breaker so a dead key
  fails fast instead of being retried forever, and ordered fallback.
- `capabilities.py` — a capability registry keyed by model-name substring, with
  a conservative default. Code asks whether a model supports JSON mode or tool
  calling; it never assumes. A new model degrades to fewer features instead of
  producing garbage.
- `pricing.py` — per-model token pricing for the usage ledger. Retired models
  stay in the table, because deleting one would silently restate historical
  usage rows as "unknown model".

### `api/prompts/` — the shared prompt library

Save, tag, search, insert; workspace-scoped and durable. Search filters in
Python because workspaces are small and correctness beats an index here.

### `engine/ouroboros/` — the deep-reasoning engine

The vendored LangGraph engine behind Deep Reasoning: `graph/` (the reason →
reflect → synthesize cycle), `memory.py`, `presets.py` (the six reasoning
modes), `usage.py`, `store.py`, `checkpointing.py`.

Its halting rule is the product claim: a run stops when successive syntheses
stop moving in embedding space (semantic convergence), not when a cycle
counter runs out. `backend/evals/FINDINGS.md` is the measured record — the
controller matched fixed-4-cycle quality at roughly half the tokens and
self-terminated on `converged` in every run rather than hitting the budget cap.

---

## 4. Data model

23 tables, 15 Alembic migrations, one schema across SQLite and Postgres.

| Group | Tables |
|---|---|
| Identity & tenancy | `users`, `workspaces`, `memberships`, `invites`, `workspace_settings` |
| The conversation graph | `conversations`, `branches`, `nodes`, `conversation_references`, `branch_votes` |
| Retrieval | `node_embeddings`, `documents`, `document_chunks`, `document_corpus_revisions`, `node_citations` |
| Runs | `deep_runs`, `resumable_runs`, `tool_calls`, `llm_calls` |
| Tools | `mcp_servers`, `mcp_tools` |
| Everything else | `prompts`, `notices` |

Two properties are worth stating explicitly because so much depends on them:

- **Nodes are immutable.** That is what makes an embedding computable once, a
  replay honest, and a fork free.
- **A branch is a pointer, not a copy.** Forking writes one row. History is a
  parent walk that crosses fork boundaries, which is why an inherited context
  is exact and a sibling branch can never leak into it.

---

## 5. Frontend

React 18 + TypeScript + Vite, built into the same container the API runs from.

```
src/
  routes/       one file per screen: AuthPage, WorkspacePicker, ChatView, MapView,
                DocsView, LibraryView, MembersView, ProviderPanel, ToolsPanel,
                McpPanel, SettingsView, AccountView, InviteView, Landing
  components/
    chat/       Composer, MessageList, BranchTree, ReplayBar, ThreadMenu,
                ExploreCompare, MentionPicker, TeamStrip, DeepButton,
                useDeepRun / useAgentRun
    monitor/    DeepReasoningMonitor, RunHistory
    map/        DecisionLedger
    shell/      Rail, TopBar, SearchOverlay
    common/     Button, Input, Dialog, Markdown, Toast, Feedback, ErrorBoundary,
                ThemeToggle
    brand/      Logo, OuroborosHelix, Frontispiece, GrainOverlay
  lib/          api, auth, sse, realtime, rbac, theme, motion, glyphs, a11y,
                format, types
  store/        session, presence, monitor, notifications, unread, insert
```

Three client-side pieces carry most of the live behaviour:

- **`lib/sse.ts`** parses the author's own run stream.
- **`lib/realtime.ts`** holds the workspace WebSocket and dispatches the same
  event vocabulary the backend emits — which is why the two sides stay in step.
- **`lib/rbac.ts`** mirrors server roles for the UI only. It decides what to
  grey out; it never decides what is allowed. The server checks every route
  independently, and a client that lies gets a 403 or a 404.

---

## 6. Security and tenancy posture

- **Identity from the JWT, always.** No route trusts a client-supplied user id.
- **RBAC server-side on every conversation, prompt and workspace route.** Reads
  require membership, writes require Collaborator or better, private threads
  are author-only, and probing a workspace you are not in reads as **404**, not
  403 — non-membership does not confirm existence.
- **Observers have exactly one write**: a team note, which never enters the
  model's context. They can address the room without being able to address
  Helix, spend the key, or alter a thread's lineage.
- **Private threads never enter the realtime room**, so they cannot leak
  through fan-out.
- **Workspace provider keys are encrypted at rest** and never appear in any
  API response. Their encryption is derived from `JWT_SECRET`, which is why
  rotating it invalidates saved keys as well as logging everyone out.
- **Tool arguments are hashed, never stored**, while every approval and denial
  records who decided.
- **Prompt injection** has an adversarial regression corpus in the test suite
  rather than a claim in a README.

Row-level security in Postgres remains a defence-in-depth step behind the
per-route checks that enforce tenancy today.

---

## 7. Observability

| Instrument | Default | What it gives |
|---|---|---|
| `GET /health` | always on | Liveness plus `durable_runs`, which tells you whether the checkpoint driver is present |
| OpenTelemetry GenAI spans | **off** unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set | Every LLM call, reasoning cycle, retrieval and tool execution as a span with `gen_ai.*` attributes. Point it at Langfuse, Jaeger, or any OTLP collector |
| `llm_calls` ledger | always on | Durable per-call token and cost accounting, surfaced at `/api/workspaces/{id}/usage` |
| `tool_calls` ledger | always on | Per-tool calls, outcomes, average latency, and who approved what |
| `deep_runs` records | always on | Each run's trace and provenance: which model and which thresholds produced it |
| Sentry | **off** unless `SENTRY_DSN` is set | Crash reporting, with `sentry-sdk` deliberately not in `requirements.txt` |

The two opt-in instruments are env-gated to a genuine no-op — no SDK, no
network client, no behaviour change — so the test suite stays hermetic and a
self-hoster never ships their errors to somebody else's account by accident.

---

## 8. Testing

**512 tests — 508 pass, 4 skipped.** Hermetic by construction: the
`stub` provider and a throwaway SQLite database mean no keys and no network are
required to run the whole suite.

```bash
cd backend && python -m pytest -q
```

Tests live beside the code they test (`api/conversation/tests/`,
`api/tools/tests/`, `api/documents/tests/`, `api/providers/tests/`,
`api/prompts/tests/`, `engine/tests/`). Coverage includes RBAC gating, the
WebSocket room, guided steer, provider resilience, durable deep runs, file
grounding, citation persistence across stores and forks, branch votes, document
metadata, the agent tool loop with its approval gate and allowlist policy, tool
spans and the tool ledger, MCP discovery and its description-drift guard, and
the adversarial injection corpus.

CI additionally runs the suite against a real **postgres:16** and applies every
migration to it on each push.

**Browser-level checks** live in `frontend/app/e2e/` and need only Node — no
`npm install`, since they import Node built-ins only:

| Script | What it drives |
|---|---|
| `smoke.mjs` | The whole golden path: register → workspace → streamed chat → upload → cited grounding → resurfacing → agent run → deep run → map. Also captures `docs/screenshots/` |
| `rooms.mjs` | Three multi-user journeys through the realtime room |
| `persistence.mjs` | Seed → restart → verify, including that a token issued before the restart still works |
| `citations.mjs` | Citations survive a reload |
| `convergence.mjs` | The halting behaviour |
| `onboarding.mjs` | The seeded example workspace |
| `responsive.mjs`, `usability.mjs`, `shots-dark.mjs` | Layout, interaction and dark-theme capture |
