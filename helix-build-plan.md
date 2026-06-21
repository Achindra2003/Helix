# Helix — Build Plan

> Companion to `helix-product.md` and `helix-srs.md`. Makes the 9-module Helix
> spec buildable by **3 people in 8 weeks**.
>
> **Helix is one collaborative AI workspace** (see `helix-product.md`) with:
> - an **everyday collaborative core** — shared/private conversations, fork tree,
>   prompt library, real-time presence — running on plain streaming chat; and
> - a **Deep Reasoning mode** — a LangGraph recursive-reasoning engine (internally
>   codenamed *Ouroboros*) a member escalates into on a hard question, served by
>   the monitor/kill/steer/budget layer.
>
> **Architecture decisions (locked):**
> 1. **Core first.** The collaborative core ships and demos on simple streaming
>    chat (Weeks 1–5); Deep Reasoning is the Weeks 6–7 headline, not a
>    critical-path dependency.
> 2. **One backend.** A single Python/FastAPI backend imports the reasoning engine
>    as an in-process module — one repo, no internal HTTP hop.
> 3. **Pluggable LLM** — Groq (hosted) or Ollama (local), via one provider
>    interface. Claude Pro is the team's *coding assistant*, not the product's brain.

---

## 0. The core and the Deep Reasoning mode

**Everyday core (M1–M5, M8, M9).** Shared/private conversations with plain
streaming replies, forkable into a branch tree, with a shared prompt library and
real-time presence. Needs no monitor or kill switch — it's normal chat fanned out
to the workspace. The whole core is built and demoable without the engine.

**Deep Reasoning mode (M6–M7, the headline).** When a member clicks "Deep
Reasoning", Helix runs the LangGraph recursive engine instead of a plain reply:
three parallel reasoners (affective / logical / analogical-memory), semantic
memory, optional research, live token streaming, reasoning topology, human-steering
pauses, and an energy/compute-budget halting controller. Because it's a
long-running autonomous process, it comes with the monitor (M7): live trace, kill
switch, steer/pause, and budget meter.

> **Product thesis:** *Helix is a collaborative AI workspace — shared, branchable
> conversations with a reusable prompt library, plus a monitored Deep Reasoning
> mode for hard problems.* (Full definition: `helix-product.md`.)

### What the engine already provides vs. what we must build

| Helix need | Engine already provides | Backend must add |
|---|---|---|
| Agent loop (M5) | The whole LangGraph reasoning graph | Tenant-scoped driver around it |
| Step/token stream (M6) | Streams `step`/`token`/`complete` w/ energy, depth, loop_guard, readings, synthesis | Route events to the *right workspace room* only |
| Kill switch (M6) | Stop halts the loop mid-cycle (`_running.discard`) | Per-run auth + RBAC gating |
| Human-steer pause (M6) | Steer + `waiting_for_input` event | Approval gate, role rules |
| Budget meter (M6) | `usage.py` token tracking; controller `compute_budget` + `stop_reason` | Per-workspace budget aggregation + alerts |
| Fork (M4) | LangGraph **checkpointing by `thread_id`**; state is a clean `TypedDict` | Copy checkpoint → new thread = fork; tree persistence |
| Replay/export (M7) | JSON/Markdown export | Workspace-scoped history, branch replay |
| Auth/tenancy/RBAC (M1/M8) | **nothing** | All of it |
| Shared context/sync (M2/M3) | **nothing — single-user** | All of it |

### Critical internal-boundary note (from the engine's current code)

The engine's existing standalone `server.py` uses **module-global state**
(`_sessions`, `_running`, `_ws_clients`) and **broadcasts to *all* connected
clients** — it's single-tenant by construction. **The backend must not
reuse that server.** Instead it imports the engine's graph as a library:

```python
from ouroboros.graph import create_ouroboros_graph
from ouroboros.usage import new_usage_handler, summarize_usage
from ouroboros.checkpointing import checkpointer_context
from ouroboros.models import OuroborosConfig
```

…and drives the graph itself, per workspace, with its own checkpointer,
WebSocket rooms, auth, DB, and fork tree. Building that tenant-scoped driver
(plus refactoring the engine away from globals) *is* the core integration work.

---

## 1. Architecture

A simple three-tier shape: a React frontend, one FastAPI backend (which also
imports the reasoning engine as a module), and PostgreSQL. The LLM is pluggable
(Groq or Ollama). Redis is **not** part of the core — it's an optional later
addition only if you need to scale across multiple backend instances.

```
   ┌─────────────────────────────┐
   │  Frontend (React)           │   Auth · Conversations · Branch Tree
   │                             │   Prompt Library · Monitor · Replay
   └──────────────┬──────────────┘
                  │  REST + WebSocket
   ┌──────────────▼──────────────┐
   │  Backend (Python / FastAPI) │   auth/RBAC · conversations · sync rooms
   │   · WebSocket rooms         │   fork tree · prompt library · replay
   │   · Reasoning engine (pkg)  │   ← deep-reasoning runs, in-process
   └───────┬──────────────┬──────┘
           │              │ pluggable provider
   ┌───────▼───┐   ┌───────▼────────┐
   │ PostgreSQL│   │ Groq │ Ollama  │
   └───────────┘   └────────────────┘

   ( Redis — optional, later: pub/sub fan-out for multi-instance scaling )
```

The **Engine Driver** (deep layer) is the heart of the M6/M7 integration: a
per-workspace class that builds an engine graph, streams its
`astream(stream_mode=["updates","messages"])` output into the *workspace's* WS
room, persists each update as a `run_step`, and exposes
start/steer/stop scoped to a `run_id`.

---

## 2. Data Model (Postgres — the core)

```
workspaces    (id, name, owner_id, created_at)
users         (id, email, pw_hash, created_at)
memberships   (user_id, workspace_id, role)             -- Owner|Collaborator|Observer
conversations (id, workspace_id, author_id, title,
               visibility, created_at)                  -- visibility: shared|private
nodes         (id, conversation_id, parent_id NULL,      -- messages + the fork tree
               branch_id, seq, author_id, role,         -- role: user|assistant|system
               content JSONB, token_count, created_at)
branches      (id, workspace_id, conversation_id, name,
               head_node_id, parent_branch_id,
               engine_thread_id, created_at)             -- engine_thread_id: deep-run only
prompts       (id, workspace_id, author_id, title,       -- shared prompt library (M5)
               body, tags JSONB, created_at)
runs          (id, workspace_id, conversation_id,        -- deep-reasoning runs (M6)
               status, provider, model, stop_reason,
               started_at, ended_at)
run_steps     (id, run_id, idx, node, payload JSONB,     -- one row per engine step (M7)
               token_count, latency_ms, created_at)
permissions   (workspace_id, role, action, allowed)      -- RBAC policy table (M9)
```

**Forking (M4) = O(1):** create a new `branch` row and point `parent_id` at the
fork node — no message history is copied (structural sharing via the `parent_id`
walk). For a **deep-reasoning** branch, additionally copy the run's LangGraph
checkpoint to a fresh `engine_thread_id` so the recursive state continues too.

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript, TailwindCSS, Vite |
| Backend | **Python 3.11 + FastAPI**, WebSockets |
| Engine | Reasoning engine package (LangGraph), imported in-process |
| Database | PostgreSQL |
| LLM | Pluggable provider — **Groq** (hosted) or **Ollama** (local) |
| Dev infra | Docker Compose (Postgres + Ollama + backend) |
| *Optional, later* | Redis (pub/sub fan-out for multi-instance scaling only) |

> The engine already has its own `pyproject.toml` and test suite — fold these
> into the Helix repo. The engine lives as a Python package (`/backend/engine`)
> imported in-process; modify it freely as part of the project. Hosting and CI
> are deployment details, not core scope — any container host works.

---

## 4. Module mapping (full spec preserved)

| Module | Layer | How it's built |
|---|---|---|
| M1 Auth & Workspace Registry | core | FastAPI + JWT; workspaces, invite links, roles, tenant isolation |
| M2 Shared & Private Conversations | core | Per-conversation visibility; plain streaming reply via provider; summarise on budget |
| M3 Real-Time Sync & Presence | core | Per-workspace WS rooms + Redis pub/sub; append-only ordered message log; presence |
| M4 Conversation Fork & Branch Tree | core | Fork = new branch + `parent_id` pointer (O(1)); branch-tree UI |
| M5 Shared Prompt Library | core | Save/tag/search prompts; insert into a conversation |
| M6 Deep Reasoning Mode | **deep** | Escalation: run the recursive engine graph via the Engine Driver instead of a plain reply |
| M7 Agent Monitor & Control | **deep** | Consume engine `step`/`token` events; kill=`stop`, pause=`steer`, budget=`usage`+`compute_budget` |
| M8 History, Replay & Export | core | Per-branch replay; export JSON/Markdown |
| M9 Permission Layer | core | Gate send/escalate/fork/library/steer/kill/tool-use by role |

The **collaborative core (M1–M5, M8, M9)** ships first on plain chat and is the
product. The **deep layer (M6–M7)** adds the recursive engine + monitor and is the
headline depth feature — the cuttable layer. Every specialisation concept is present:
Agentic AI (deep layer), Distributed Systems (sync/log/pub-sub), RBAC (M1/M9), with
persistent trees (M4) as a natural fourth.

---

## 5. Team Split

- **A — Backend & Infra:** FastAPI app, Postgres schema/migrations, auth +
  RBAC, Redis, per-workspace WS rooms + pub/sub, deploy, CI.
- **B — Frontend & UX:** React app, auth/workspace UI, shared chat + streaming,
  presence, **branch-tree viz**, **monitor dashboard**, replay viewer.
- **C — Engine & Integration:** the reasoning-engine package itself + the
  **Engine Driver** (refactor away from globals, embed the graph), per-tenant
  checkpointing + fork, step-event normalisation, budget/kill/steer wiring,
  provider config (Groq/Ollama).

---

## 6. Week-by-Week Roadmap

> **Sequencing principle:** build the whole collaborative spine on the **chat
> gear** first (Weeks 1–5, low risk, always demoable), then bolt on the **Deep
> Reasoning gear + monitor** (Weeks 6–7). The engine is never on the critical path.

### Week 0 — Pre-flight
- [ ] Repo + monorepo layout (`/frontend`, `/backend/api`, `/backend/engine`, `/shared`).
- [ ] Fold the existing engine code into `/backend/engine` as a package (used later).
- [ ] `docker-compose up` → Postgres + Ollama + Helix backend.
- [ ] Agree shared schemas (Node, Branch, StepEvent, EngineConfig).
- **Gate:** stack runs locally.

### Weeks 1–2 — Foundation (M1, M2)
- **A:** Auth (JWT), workspaces, memberships/roles, full DB schema.
- **C:** LLM **provider interface** (Groq + Ollama); **shared & private
  conversations** with plain streaming chat (no engine yet).
- **B:** Auth + workspace UI; conversation list (shared/private) + chat view.
- **Gate (W2):** logged-in user creates a shared/private conversation and sees a
  streamed reply from a free model.

### Weeks 3–4 — Collaboration & Sync (M3)
- **A:** Per-workspace WS rooms (in-memory), presence, append-only ordered
  message log with sequence numbers. *(Redis pub/sub is an optional later add-on,
  only needed to fan events across multiple backend instances.)*
- **C:** Shared context handling — token budgeting, sliding-window summarisation.
- **B:** Multi-user shared view, presence avatars, stream fan-out to N clients.
- **Gate (W4):** 2+ users hold one shared, ordered, streamed conversation.
  **Core demo #1.**

### Week 5 — Fork tree + Prompt library (M4, M5)
- **C/A:** Fork a conversation via `parent_id` pointers (O(1)); branch context.
- **B:** Git-style branch-tree sidebar; **shared prompt library** (save, tag,
  search, insert into a conversation).
- **Gate:** fork a conversation (both branches continue); save and reuse a prompt.

### Weeks 6–7 — Deep Reasoning Mode + Monitor (the headline) (M6, M7)
- **C:** **Engine Driver** — import `create_ouroboros_graph`, run a
  workspace-scoped engine session on escalation; refactor engine off globals;
  optionally extend fork to copy the LangGraph checkpoint to a new `thread_id`.
- **A:** Persist engine `step` events → `run_steps`; stream over the sync layer;
  wire `stop` (kill), `steer` (pause), `usage`+`compute_budget` (budget meter).
- **B:** "Deep Reasoning" escalation button + live monitor — reasoning topology,
  energy/depth/loop_guard, **kill switch**, **steer box**, **budget meter**.
- **Gate (W7):** escalate a hard question, watch the recursive trace live, steer
  it, kill it mid-loop, see the budget meter. **Core demo #2 (the escalation).**

### Week 8 — Hardening & Demo (M8, M9)
- **A:** Postgres RLS (tenant isolation); deploy frontend + backend + DB;
  sync-latency test (<200ms).
- **C:** M8 — per-branch replay + JSON/Markdown export.
- **B:** M9 — role-gated actions + Deep Reasoning tool allowlist; approval gate.
- **All:** demo video, README.
- **Gate:** full deployed demo.

---

## 7. Cut Lines (only if behind — cut in this order)

1. M9 → static role rules, no per-tool approval UI.
2. Postgres RLS → app-layer tenant filtering only.
3. LLM summarisation → sliding-window truncation.
4. Markdown export → JSON only.

*(Single backend instance with in-memory WS rooms is the baseline, not a cut —
Redis/multi-instance scaling is explicitly out of core scope.)*

**Never cut:** M1 auth, M2 conversations, M3 sync, M4 fork tree, M5 prompt library
(the collaborative core). If Weeks 6–7 slip, the deep layer (M6/M7) can ship as a
reduced "single live monitored run" — the core product still demos fully.

---

## 8. Minimum Viable Demo

1. Two users in one workspace holding a shared, ordered, streamed conversation (M1–M3).
2. Fork the conversation into a branch; both continue independently (M4).
3. Save a prompt to the **shared library** and reuse it (M5).
4. Escalate a hard question to **Deep Reasoning**; watch the live trace, steer it,
   and kill it mid-loop with the budget meter visible (M6–M7).

---

## 9. Free-Tier Risk Notes

- **Provider rate limits:** the engine's `compute_budget` halting controller and
  the ordered message log bound token spend. Use Ollama in dev to avoid hosted limits.
- **Ollama RAM (~8GB):** teammates who can't run it set `LLM_PROVIDER=groq`.
- **Refactoring the engine off globals (M6):** the standalone server's global
  state is the one real integration hurdle — but it sits in Weeks 6–7, off the
  critical path, so it can't sink the core product.
- **Embeddings block the event loop:** the engine's semantic-memory/stability
  embeddings are CPU-bound — offload to a thread pool so one deep run can't stall
  other workspaces' streams.
- **Realtime is the second hard part:** keep shared state an append-only,
  server-ordered log (no concurrent co-editing); lean on Socket.io for reconnection.
- **Tool-calling quality:** small Ollama models reason worse — test Deep Reasoning
  on Groq's 70B.

---

_Plan v5 — grounded shape: collaborative core (M1–M5, M8, M9) built first
(Weeks 1–5); Deep Reasoning + monitor (M6–M7) is the Weeks 6–7 headline. Simple
three-tier stack (React · FastAPI · PostgreSQL); pluggable LLM (Groq/Ollama);
Redis optional for scaling only. See `helix-product.md` and `helix-srs.md`._
