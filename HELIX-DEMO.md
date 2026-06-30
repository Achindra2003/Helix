# Helix — Demo Guide

**One-line pitch:** *Helix is "Git for your team's AI work" — shared, branchable
AI conversations, a reusable prompt library, and an escalation to deep reasoning.*

There are **three ways to demo**. Use the **clickable UI** (Option C) as the
showpiece; the **narrated script** (Option A) is the reliable no-browser baseline;
the **live API** (Option B) is the raw contract Rajnish's UI attaches to.

---

## Prerequisites (one-time)
- Python venv is set up at `backend/.venv`.
- `backend/.env` holds the Groq config (already created):
  ```
  LLM_PROVIDER=groq
  GROQ_API_KEY=<key>
  GROQ_MODEL=llama-3.1-8b-instant
  ```
  The light `8b-instant` model is used deliberately so a live demo doesn't hit
  Groq free-tier rate limits.

---

## Option C — The product app (the showpiece) ⭐

The real React + TypeScript app (`frontend/app/`) in an illuminated-manuscript /
scholarly-codex look (parchment, gold, red rubric ink, a double-helix frontispiece),
wired to the live backend. **Real** auth, workspaces, streaming, forking,
prompt reuse, and deep reasoning — nothing is faked. (The old single-file
`frontend/helix.html` is kept as a no-build fallback.)

**One command (from the repo root):**
```
./frontend/run-demo.ps1
```
Starts the API on `:8000`, installs deps on first run, starts the app on `:5173`,
and opens the browser. Requires **Node 18+**.

**Manual (two terminals):**
```
# terminal 1 — backend
cd backend && ./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
# terminal 2 — frontend
cd frontend/app && npm install && npm run dev
```
Then open **http://localhost:5173**.

> ⚠ The app must run on **port 5173** — the backend's CORS only allows that origin
> (Vite is configured with `strictPort`).

### Demo path (what to click)
1. **Sign in / create account** — real JWT auth; the screen shows a live
   `api ✓ (groq)` badge. Then **create or pick a workspace**.
2. **Chat with shared context** — new conversation, type a question, watch the
   reply **stream token by token**. Add a follow-up — it uses the whole thread.
3. **Fork (the novelty)** — hover a message → **fork here** (or the **Fork**
   button); name a branch. It inherits the ancestor context and appears in the
   **branch lineage**; switch branches to show isolation.
4. **Prompt library** — **LIBR** in the rail; search, **Insert →** a saved prompt
   to drive a turn back in the conversation.
5. **Deep Reasoning** — type a hard question, click **Deep Reasoning**. The right
   monitor shows the live **reason→reflect→synthesize trace**, the **energy +
   budget meters**, then it **converges** (`converged`) with a crystallized
   answer in ~7s. Hit **Kill switch** mid-run to stop it.
6. **Replay & export** — use the **replay** scrubber in the conversation header to
   step through the thread; **↓ md / ↓ json** export the branch.
7. **Members & Roles** — **TEAM** in the rail: members, invites, and the permission
   matrix. Flip the role switch (top-right) to **Observer** → the workspace goes
   read-only.

Notes: the prompt library is seeded with starters on a workspace's first visit.
**Presence/live-watch** shows "you only" until the WebSocket room is built.
**Steer** (pause→inject→resume) is proven
in Option A but not yet wired over HTTP, so the live monitor shows trace + budget
+ converge + kill.

---

## Option A — Narrated script (reliable, no UI needed)

From `backend/`:
```
./.venv/Scripts/python.exe -m api.demo_helix
```
Runs the whole story end-to-end against real Groq and prints evidence at each
step. A captured run is saved at `demo_artifacts/demo_transcript.txt` (use it as
a backup if the network is flaky on demo day). Takes ~1–2 minutes.

### What it shows + what to say
1. **Shared, branchable context** — Alice asks, Bob follows up with "given that,
   which is simplest?" and the AI answers correctly using the *whole thread*.
   > "Everyone shares one context. The assistant sees the team's full thread."
2. **Fork & branch (the novelty)** — Bob forks Alice's thread and explores a
   different angle; Alice keeps going on the original. The isolation proof prints
   five `True` lines.
   > "This is the Git moment: fork a teammate's thread, inherit their context,
   > diverge — and the branches never leak into each other."
3. **Shared prompt library** — save a winning prompt, search it, reuse it to drive
   a turn in a brand-new conversation.
   > "A team's best prompts become a reusable asset."
4. **Deep Reasoning (Ouroboros)** — escalate a hard question:
   - live reasoning **trace** + **token-budget meter**,
   - **converges** (`stop_reason=converged`) instead of burning the whole budget,
   - **kill** mid-run,
   - **steer**: pause → inject human input → resume.
   > "For hard calls, escalate to a recursive reasoner that self-halts when the
   > answer stabilizes — and you can stop or steer it."
5. **Export** — dump a conversation to Markdown + JSON.

---

## Option B — Live API (for the UI)

Start the server from `backend/`:
```
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
```
Health check: `GET http://127.0.0.1:8000/health` → `{"status":"ok",...,"provider":"groq"}`

### Endpoints the UI consumes (all verified working)
| Action | Method & path |
|--------|---------------|
| Create conversation | `POST /conversations` |
| Send a message (SSE stream) | `POST /conversations/{branch_id}/messages` |
| Fork a branch | `POST /conversations/{conversation_id}/fork` |
| Branch history | `GET /conversations/branches/{branch_id}/history` |
| Escalate to deep reasoning (SSE) | `POST /conversations/{branch_id}/deep` |
| Save prompt | `POST /workspaces/{workspace_id}/prompts` |
| List/search prompts | `GET /workspaces/{workspace_id}/prompts?q=&tag=` |
| Get prompt | `GET /prompts/{prompt_id}` |
| Insert prompt as a turn (SSE) | `POST /conversations/{branch_id}/messages/from-prompt` |

**SSE event shape:** each frame is `data: {json}` with a `kind` field
(`user_node` → `token`* → `assistant_node`, then `[DONE]`). Deep reasoning adds
`step`, `budget`, `waiting`, `complete`.

---

## Honest caveats (good to pre-empt)
- **No auth on the conversation/prompt routes yet** — that's the next backend task
  (Mansoor): gate them by login + workspace membership.
- **Deep-reasoning convergence thresholds are calibrated** to the active embedder;
  the "self-halts when stable" behaviour is real but tuned.
- The lighter chat model is used for rate-limit safety; production can switch to a
  larger model for higher answer quality.

## Run the tests (proof of correctness)
From `backend/`: `./.venv/Scripts/python.exe -m pytest -q` → **39 passing.**
