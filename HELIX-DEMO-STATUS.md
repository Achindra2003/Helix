# Helix — What We Can Demo Now (status + how it works)

This is the honest, current picture: **what you can show today**, **what's done vs. coming**,
and for each working feature — **what it does, why it matters, and how it actually works**.

> One line: **Helix is "Git for your team's AI work"** — a shared, multi-tenant workspace
> where AI conversations can be *branched*, reusable prompts are kept in a shared library,
> and any hard question can be *escalated* to a self-halting deep-reasoning engine, all under
> role-based access control.

**Ground truth as of this writing:** backend **43/43 tests passing**, frontend builds clean,
both run live (React + Vite UI on `:5173`, FastAPI + SSE API on `:8000`) against a real LLM
provider (Groq). Nothing in the demo is faked — every click hits the live API.

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
| FR-3 | Role-based access control | 🟡 | Roles + permission matrix; **enforced in the UI**, not yet server-side |
| FR-4 | Shared & private conversations | ✅ | Shared streaming chat; **private is enforced** — only the author sees it |
| FR-5 | Real-time sync & presence | ⬜ | *Not built* — no live "who's online" (needs WebSocket) |
| FR-6 | Fork & branch tree | ✅ | Fork, branch lineage, context inheritance + isolation |
| FR-7 | Shared prompt library | ✅ | Save / search / insert prompts |
| FR-8 | LLM provider abstraction | ✅ | Provider label; swap groq/ollama/stub via config |
| FR-9 | Deep Reasoning mode | ✅ | Escalate → recursive run that converges |
| FR-10 | Deep Reasoning monitor | ✅ | Live trace, depth/energy/budget meters |
| FR-11 | Run control — kill & steer | 🟡 | **Kill works**; **Steer** present-but-disabled (not over HTTP yet) |
| FR-12 | Budget meter & guardrails | ✅ | Budget bar; run bounded, halts before runaway |
| FR-13 | History, replay & export | ✅ | Replay scrubber + Markdown/JSON download |
| FR-14 | Tool permission layer | ⬜ | *Future* — per-role tool allowlist for Deep Reasoning |

**Score:** 10 fully done, 2 partial (with honest limits), 2 planned.

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

### 🟡 FR-11 — Run control: Kill works, Steer is staged
- **What works:** A **Kill switch** stops a live run immediately.
- **How:** Kill aborts the streaming `fetch` (`AbortController`); the server sees the dropped
  stream and finalises the run as killed — a clean, cooperative stop.
- **Limit:** **Steer** (pause → inject guidance → resume) is *proven in the engine* and shown
  in the narrated backend demo, but isn't wired over HTTP yet, so its button is present-disabled.

### ✅ FR-13 — History, replay & export
- **What:** Persisted threads can be replayed step-by-step and exported.
- **How:** `get_history` already yields the ordered nodes; a replay scrubber walks them
  client-side, and an export endpoint assembles the branch into Markdown or JSON for download.

### 🟡 FR-3 — RBAC (Owner ⊃ Collaborator ⊃ Observer)
- **What works:** Roles exist, a "policy as data" permission matrix is shown, and the role
  switch **re-skins the UI to read-only for Observers**.
- **How:** The client uses an RBAC policy map to hide/disable controls per role.
- **Limit:** The **server doesn't yet enforce** these on the chat/prompt routes — so it's a
  trustworthy *preview*, not a security boundary. (See "Planned" below.)

---

## What's planned — and why it isn't done yet

These four are honestly incomplete. Three are one backend lane (the auth/real-time/run-control
work); the frontend is already built with seams so they light up with **no UI rework**.

| Item | Maps to | Why not yet / what's needed |
|---|---|---|
| **Auth-gate & enforce tenancy** on chat/prompt routes | FR-3, NFR-2/5 | Engine + auth exist separately; chat routes still run un-gated (the client passes `viewer_id`/`author_id` rather than the server reading the JWT). Private-conversation visibility is now filtered; the remaining work is server-side membership/role enforcement on each route. |
| **Real-time presence + live-watch** | FR-5, NFR-1/7 | No WebSocket layer yet. Needs a presence channel to broadcast "who's online" and live message fan-out. This is the one *visibly* stubbed feature. |
| **Server-side steer/resume over HTTP** | FR-11 (steer) | The engine supports pause→inject→resume; it isn't exposed as an HTTP run-control endpoint yet. Kill (abort) is the interim. |
| **Per-role tool allowlist** for Deep Reasoning | FR-14 | Future: let an Owner restrict which tools a deep run may use, with approval. Not started. |

**Why this framing is the right one for the panel:** the *hard* parts — the branchable shared
context, the self-halting budgeted reasoning engine, the provider seam — are done and provable.
The remaining items are mostly *integration/enforcement* plumbing on top of pieces that already
exist, which is exactly the honest place to be at this milestone.

---

## Honest caveats (say these before someone finds them)
- **Serve the UI on `:5173`** — the backend's CORS only allows that origin; `file://` is blocked.
- **Roles are a UI preview, not yet a server boundary** — don't claim tenant security is enforced. (Private-conversation visibility *is* now enforced server-side; cross-route membership/role checks are the remaining gap.)
- **No live presence** — "3 online" style indicators aren't real yet.
- **Keep Deep Reasoning questions focused** so the converge lands in ~7s on the free Groq tier.
- Verified via the live API + tests + the page serving; **do one real click-through** before presenting.

---

*Related docs:* `REQUIREMENTS-COVERAGE.md` (full SRS traceability) · `HELIX-USAGE.md`
(click-by-click) · `HELIX-DEMO-SCRIPT.md` (who presents what) · `HELIX-STORY.md` (narrative).
