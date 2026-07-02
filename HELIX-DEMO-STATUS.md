# Helix — What We Can Demo Now (status + how it works)

This is the honest, current picture: **what you can show today**, **what's done vs. coming**,
and for each working feature — **what it does, why it matters, and how it actually works**.

> One line: **Helix is "Git for your team's AI work"** — a shared, multi-tenant workspace
> where AI conversations can be *branched*, reusable prompts are kept in a shared library,
> and any hard question can be *escalated* to a self-halting deep-reasoning engine, all under
> role-based access control.

**Ground truth as of this writing (v2, branch `v2-complete`):** backend **64/64
tests passing**, frontend builds clean, both run live (React + Vite UI on `:5173`,
FastAPI + SSE + WebSocket API on `:8000`) against a real LLM provider (Groq —
chat on the fast 8B, deep reasoning on the 70B). Nothing in the demo is faked —
every click hits the live API, and a scripted 2-user end-to-end (presence, live
fan-out, guided steer) passes 15/15.

---

## How to run it (for the demo)

```
./frontend/run-demo.ps1          # starts API (:8000) + UI (:5173), opens the browser
```
Or manually, two terminals:
```
cd backend  && ./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
cd frontend/app && npm run dev   # serves on :5173 (the origin the backend's CORS allows)
```
Confirm the green **`api ✓ (groq)`** badge on the sign-in screen before presenting.

---

## The demo you can give right now (happy path)

A single ~8-minute flow that exercises every finished pillar:

1. **Sign in → workspace.** Real account (JWT), land in a team workspace.
2. **Shared streaming conversation.** Ask a question; the answer **streams token-by-token**.
   A follow-up uses the **whole thread** as context.
3. **Fork.** Branch the conversation at any node; the branch **inherits the prior context**
   then diverges in **isolation** from its siblings. *(This is the signature moment.)*
4. **Prompt library.** Search a saved prompt, **Insert →** runs it as a turn.
5. **Deep Reasoning.** Escalate a hard question; the right-hand monitor shows a live
   **reason → reflect → synthesize** trace with **energy/budget meters**, then it
   **self-halts (converged)** in ~7s. The **Kill switch** stops a run on command.
6. **Replay & export.** Step back through the thread; **download** it as Markdown/JSON.
7. **Roles.** Flip the role switch to **Observer** — the workspace goes read-only.

---

## Feature status at a glance

Legend: ✅ done & demoable · 🟡 partial (works, with a named limit) · ⬜ planned

| # | Feature (SRS) | Status | What you'll see in the demo |
|---|---|---|---|
| FR-1 | Auth & accounts | ✅ | Register / sign in, session persists on reload |
| FR-2 | Workspaces & multi-tenancy | ✅ | Create a workspace, members list |
| FR-3 | Role-based access control | ✅ | Roles + permission matrix; **enforced server-side on every route** (Observer read-only at the API) |
| FR-4 | Shared & private conversations | ✅ | Shared streaming chat; **private is enforced** — only the author sees it (lists, fetches, and the realtime room) |
| FR-5 | Real-time sync & presence | ✅ | WebSocket room per workspace: live "who's online", teammates' turns stream into your open thread token-by-token |
| FR-6 | Fork & branch tree | ✅ | Fork, branch lineage, context inheritance + isolation |
| FR-7 | Shared prompt library | ✅ | Save / search / insert prompts; teammates' saves appear live |
| FR-8 | LLM provider abstraction | ✅ | Provider label; swap groq/ollama/stub via config; deep reasoning on its own 70B model |
| FR-9 | Deep Reasoning mode | ✅ | Escalate → recursive run that converges (semantic MiniLM stability) |
| FR-10 | Deep Reasoning monitor | ✅ | Live trace, depth/energy/budget meters; teammates can live-watch a shared run |
| FR-11 | Run control — kill & steer | ✅ | **Kill works**; **⟂ guided** runs pause between cycles and resume with injected guidance over HTTP |
| FR-12 | Budget meter & guardrails | ✅ | Budget bar; run bounded, halts before runaway |
| FR-13 | History, replay & export | ✅ | Replay scrubber + authenticated Markdown/JSON download |
| FR-14 | Tool permission layer | 🟡 | Server-side research policy flag; per-role allowlist UI is future |

**Score:** 13 fully done, 1 partial (with an honest limit).

---

## What works — and *why* and *how*

### ✅ FR-1/2 — Accounts & workspaces
- **What:** Register/login issue a JWT; users create workspaces and are added as members.
- **Why it matters:** It's the multi-tenant "team room" — the thing a *shared* workspace needs.
- **How:** FastAPI auth routes hash passwords and sign a JWT; the React client stores the
  token and rehydrates the session via `/me` on reload. Workspace + membership rows back it.

### ✅ FR-4 — Shared, streaming conversations
- **What:** Any member's message streams a live AI reply; later turns see the full thread.
- **Why:** This is the core "one shared context" promise — the team thinks in one place.
- **How:** A message turn `POST`s to `/conversations/{branch}/messages` and the server
  returns **Server-Sent Events over POST** (`data: {json}` frames ending in `[DONE]`). The
  browser reads the stream with a `ReadableStream` reader. Server-side, `build_messages`
  (`backend/api/conversation/context.py`) renders the branch's node history into proper
  `system`/`user`/`assistant` roles, annotating each user turn with its author (`[name]`)
  so the model can tell teammates apart in one shared thread — then the provider streams the
  reply token-by-token.

### ✅ FR-6 — Fork & branch tree (the signature feature)
- **What:** Fork a conversation at any node into a new branch that *inherits* everything up
  to that point, then evolves independently. Siblings don't leak into each other.
- **Why:** It's the "Git for AI" idea — explore two directions from a shared starting point
  without losing the original or contaminating it. No other AI chat tool does this cleanly.
- **How:** A branch stores a `parent_branch_id` and the node it forked from. `get_history`
  walks the `parent_id` **spine across fork boundaries**, so a branch's history = its
  ancestors' nodes + its own, and **nothing** from sibling branches. Forking is O(1)
  (a pointer, not a copy); isolation is structural, not a filter. The lineage tree in the
  left pane renders those parent links as Git-style indentation.

### ✅ FR-7 — Shared prompt library
- **What:** Save a prompt once (title/body/tags); anyone searches and inserts it as a turn.
- **Why:** Captures "what worked" so good prompting is reused, not re-typed — team knowledge.
- **How:** Prompts persist per-workspace. **Insert** calls
  `/conversations/{branch}/messages/from-prompt`, which materialises the saved body as a real
  user node and streams the reply exactly like a normal turn — so a reused prompt behaves
  identically to a typed one and stays in the shared thread.

### ✅ FR-8 — Provider abstraction
- **What:** All inference goes through one seam; groq / ollama / a deterministic stub are
  interchangeable.
- **Why:** Model-agnostic by design — no vendor lock-in, and tests/demos can run offline.
- **How:** A provider `Protocol` (`stream_messages`) with concrete implementations. Groq does
  native multi-turn; the stub echoes (for tests); Ollama flattens. The active one is chosen by
  config/`.env`, surfaced as the provider label in the UI.

### ✅ FR-9/10/12 — Deep Reasoning + monitor + budget (the power feature, *Ouroboros*)
- **What:** Escalate a hard question into a recursive **reason → reflect → synthesize** loop
  that runs autonomously and **stops itself** when the answer settles, with a live monitor
  (depth, energy, a budget meter) the whole time.
- **Why:** It's the differentiator — controlled, *interruptible*, *cost-bounded* deep thinking
  instead of a single shot. The honest engineering story is the halting + budget, not magic.
- **How:** The engine (`backend/engine/ouroboros`) is a small graph controller that loops
  reasoning nodes, seeded with recent thread context (`render_seed`) so it reasons over the
  discussion, not one line. Two guardrails make it demo-safe and trustworthy:
  - **Convergence:** an adaptive run halts when successive steps stop changing —
    `stability_threshold = 0.78` emits a real `stop_reason: converged`.
  - **Budget:** `compute_budget = 4` caps the loop so it can never run away; the meter
    reflects spend and the run ends with a clear stop reason.
  The server streams `step` / `budget` / `token` / `complete` events; the monitor renders them
  live. Result: a real ~7s converging run, not a fixed canned animation.

### ✅ FR-11 — Run control: Kill and Steer both work
- **Kill:** aborts the streaming `fetch` (`AbortController`); the server sees the dropped
  stream and finalises the run as killed — a clean, cooperative stop.
- **Steer (guided runs):** tick **⟂ guided** next to Deep Reasoning. The adaptive loop pauses
  at a steer checkpoint between refinement cycles; the monitor opens a violet steer box —
  type guidance (or "Continue as-is") and the run resumes from its LangGraph checkpoint over
  `POST /conversations/deep/runs/{run_id}/steer`. Any Collaborator in the workspace can steer,
  which makes a paused run a *team* decision point. Verified live: injecting a constraint
  mid-run visibly pivoted the converged answer.

### ✅ FR-13 — History, replay & export
- **What:** Persisted threads can be replayed step-by-step and exported.
- **How:** `get_history` already yields the ordered nodes; a replay scrubber walks them
  client-side, and an export endpoint assembles the branch into Markdown or JSON for download.

### ✅ FR-3 — RBAC (Owner ⊃ Collaborator ⊃ Observer)
- **What works:** Roles are a real **server-side security boundary**: every conversation and
  prompt route derives identity from the JWT (client-supplied ids are gone from the wire),
  checks workspace membership, and gates writes on Collaborator+. Private threads are
  author-only; outsiders get 404s, never confirmation a resource exists. The UI's permission
  matrix and Observer re-skin mirror what the server enforces.
- **How:** shared `_require_membership` / `_require_conversation` guards on each route +
  the same gate on the WebSocket room; invites carry a role (collaborator/observer).

### ✅ FR-5 — Real-time presence + live fan-out (the WebSocket room)
- **What:** One room per workspace at `/ws/workspaces/{id}` (JWT-gated). The presence bar
  shows who's really online; a teammate's turn on the thread you have open **streams in
  token-by-token**; new conversations, forks, references, and saved prompts appear without a
  refresh. If a teammate runs Deep Reason on your open branch, your idle monitor
  **live-watches their reasoning trace**.
- **How:** the HTTP routes relay run events into the room (shared threads only — private
  turns never leave their author's stream; the sender is excluded since their SSE already
  carries everything). In-process rooms behind a two-function seam (`broadcast`/`roster`) —
  a Redis pub/sub swap for multi-process scale touches one module.

---

## What's still future (say it plainly)

| Item | Maps to | Status |
|---|---|---|
| **Per-role tool allowlist UI + approvals** for Deep Reasoning | FR-14 | The policy exists server-side (`DEEP_REASONING_ALLOW_RESEARCH`, and research requires a Tavily key); the Owner-facing UI is future. |
| **Postgres row-level security + migrations** | NFR-2 | API-layer tenancy is enforced everywhere; RLS is a prod-deploy hardening step. |
| **Redis-backed rooms** | NFR-4 | Needed only for multi-process deployment; the seam is ready. |

---

## Honest caveats (say these before someone finds them)
- **Serve the UI on `:5173`** — the backend's CORS only allows that origin; `file://` is blocked.
- **Keep Deep Reasoning questions focused** so the converge lands fast on the free Groq tier
  (deep runs use the 70B model; chat stays on the 8B).
- Rooms are in-process: one API process for now (fine for the demo and small teams).
- Verified via the live API + 64 tests + a scripted 2-user end-to-end; still **do one real
  click-through** before presenting.

---

*Related docs:* `REQUIREMENTS-COVERAGE.md` (full SRS traceability) · `HELIX-USAGE.md`
(click-by-click) · `HELIX-DEMO-SCRIPT.md` (who presents what) · `HELIX-STORY.md` (narrative).
