# Helix — How to Use (step-by-step)

A practical, click-by-click guide to running and using everything built so far.
For each feature you get: **what to do**, and **what you should see**.

---

## Part 1 — Start it up

### 1.1 Prerequisites (one-time)
- **Python** virtualenv at `backend/.venv` (already set up).
- **`backend/.env`** present with Groq config (already created):
  ```
  LLM_PROVIDER=groq
  GROQ_API_KEY=<key>
  GROQ_MODEL=llama-3.1-8b-instant
  ```
- **Node.js 18+** installed (check: `node --version`).

### 1.2 Start everything (one command)
From the repo root, in a normal terminal (PowerShell):
```
./frontend/run-demo.ps1
```
This: starts the API on **:8000**, installs frontend deps on first run, starts the
app on **:5173**, and opens your browser. Two terminal windows will open — **leave
them running**.

### 1.3 Start manually (two terminals) — alternative
```
# Terminal 1 — backend
cd backend
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000

# Terminal 2 — frontend
cd frontend/app
npm install        # first time only
npm run dev
```
Then open **http://localhost:5173**.

> ⚠ The app must be on **port 5173** — the backend only allows that origin (CORS).
> Don't open the file directly; use the URL.

### 1.4 Confirm it's healthy
- Browser shows the **Helix sign-in screen** with a double-helix illustration.
- Bottom of the sign-in card shows a green **`api ✓ (groq)`** badge.
- If it says **`api offline`** (red) or a red banner appears at the top → the
  backend isn't running. Start Terminal 1 (1.3) and refresh.

---

## Part 2 — Account & workspace

### 2.1 Create an account
1. On the sign-in screen, click the **Create account** tab.
2. Enter an email and password (password must be a few characters; the prefilled
   `maren@cipherlabs.io` / `alchemist` also works for **Sign in** if you reuse it).
3. Click **Create account ⟶**.
4. **You should see:** the **Workspaces** screen.

> To log in later: use the **Sign in** tab with the same email/password. Your session
> persists across refreshes (the token is stored).

### 2.2 Create a workspace
1. On the Workspaces screen, click **+ New workspace**.
2. Type a name (e.g. `Cipher Labs`) → **Create**.
3. **You should see:** you enter the workspace — a left rail, a top bar with the
   workspace name, your role badge (**♔ Owner**), and an empty chat view.

### 2.3 (Optional) Invite a teammate
1. Left rail → **TEAM** (the ♔ icon).
2. Click **+ Invite** → a dialog shows an **invite token**; click **Copy token**.
3. The teammate signs in on their machine → Workspaces → **Join via invite** →
   pastes the token → **Join**. They appear in the members list as a Collaborator.

---

## Part 3 — Conversations (chat)

### 3.1 Start a conversation
1. You're on the **CHAT** view (rail, top icon). Left pane = **Conversations**.
2. Click the **+** next to "Conversations".
3. Type a title (e.g. `Retrieval chunking strategy`).
4. Choose **⊙ Shared** (whole workspace) or **◍ Private** (only you) → **Create**.
5. **You should see:** the conversation open in the center with "A blank page".

### 3.2 Send a message (live streaming)
1. In the composer at the bottom, type a question (e.g. *"What chunking strategy
   should we use for long PDFs?"*).
2. Press **Enter** (or click the **↑** button). Shift+Enter makes a new line.
3. **You should see:** your message appears, then **Helix's reply streams in
   token-by-token** with a blinking cursor, ending with a token/provider line
   (`… tokens · ☁ groq`).

### 3.3 Prove shared context (the assistant sees the whole thread)
1. Send a **follow-up** that depends on the previous answer, e.g.
   *"Given that, which option is simplest to ship?"*
2. **You should see:** the reply references the earlier options — it's reasoning over
   the full thread, not just your last line.

---

## Part 4 — Fork & branches (the core idea)

### 4.1 Fork a conversation
There are two ways:
- **Hover any message** → click the small **⌇ fork here** that appears, **or**
- Click the **⌇ Fork** button in the conversation header (forks at the latest message).

1. Do one of the above → a dialog opens. Name the branch (e.g. `semantic-split`) →
   **Fork**.
2. **You should see:** the **Branch lineage** section (left pane, lower) now lists
   `main` and your new branch indented beneath it; the new branch is active, and it
   already contains the inherited history up to the fork point (marked **⌇ fork point**).

### 4.2 Diverge, and prove isolation
1. On the new branch, send a message.
2. In **Branch lineage**, click **main** to switch back.
3. **You should see:** main does **not** contain the message you just sent on the
   fork — the branches are independent, but the fork still inherited main's earlier
   context. (That's the "Git for AI" property.)

---

## Part 5 — Prompt library

### 5.1 Browse & search
1. Left rail → **LIBR** (▦ icon).
2. **You should see:** a grid of prompt cards (seeded with starters on first visit),
   each with a title, body, and tags.
3. Type in the **search** box to filter by title, body, or tag.

### 5.2 Save a prompt
1. Click **+ Save prompt**.
2. Fill **Title**, **Prompt body**, and optional **Tags** (comma-separated) → **Save**.
3. **You should see:** your prompt appears in the grid; search finds it.

### 5.3 Reuse a prompt in a conversation
1. On any card, click **Insert →**.
2. **You should see:** the app switches to **CHAT** and **runs that prompt as a turn**
   in the active conversation (streaming reply). A saved prompt drove a new turn.

---

## Part 6 — Deep Reasoning (the power mode)

### 6.1 Escalate a hard question
1. Go to a conversation (CHAT). In the composer, type a hard question, e.g.
   *"Monolith or microservices for a 3-person startup? One line."*
2. Click the **⟳ Deep Reasoning** button (next to Library).
3. **You should see:** the **right-hand monitor** comes alive:
   - the **topology strip** (reason → reflect → synthesize → breathe → surface)
     lighting up as it runs,
   - the **Ouroboros ring** showing **depth**,
   - **ENERGY** and **BUDGET** meters moving,
   - readings: **loop-guard / stability / confidence / tokens**,
   - a live **step trace** of the reasoning.

### 6.2 Watch it converge
1. Wait ~7 seconds.
2. **You should see:** a **Crystallized answer** box, and a status line
   **`✓ converged`** — it self-halted when the answer stabilized (not from running out
   of budget). The answer is also saved into the conversation thread.

### 6.3 Kill a run on command
1. Start another Deep Reasoning run.
2. While it's running, click **◼ Kill switch**.
3. **You should see:** the run stops immediately and shows **`killed`**.

> Note: the **⟂ Steer** button is intentionally **disabled** — pause/inject/resume
> is built into the engine but not yet wired through the live API.

---

## Part 7 — History, replay & export

### 7.1 Replay a thread step by step
1. In a conversation with several messages, find the **▷ replay** control in the
   conversation header.
2. Click it, then drag the slider.
3. **You should see:** the thread reveals one message at a time up to the slider
   position (`n/total`). Click **● replay** again to return to the full view.

### 7.2 Export
1. In the conversation header, click **↓ md** or **↓ json**.
2. **You should see:** a file downloads — Markdown (readable transcript) or JSON
   (structured: conversation + branch + nodes).

---

## Part 8 — Members, roles & permissions

### 8.1 See the team and the policy
1. Left rail → **TEAM**.
2. **You should see:** the member list (avatar, email, role) and the **Permission
   Matrix** showing which role can do what (✓ / ·).

### 8.2 Change a role (Owner only)
1. Next to a member, use the **role dropdown** to change their role → it saves.

### 8.3 Preview the workspace as each role
1. Top-right, use the **role switch** (♔ / ⌇ / ◉).
2. Switch to **◉ Observer**.
3. **You should see:** the workspace **dims** and all write actions disappear — no
   composer, no Fork, no Deep Reasoning. A read-only notice replaces the composer.
4. Switch back to **♔ Owner** to restore full control.

### 8.4 Sign out
- Click the **logo** at the top of the left rail to return to the workspace picker,
  or sign out from the workspaces screen.

---

## Part 9 — Backend-only options (no browser)

- **Narrated end-to-end run** (proves the whole engine without UI):
  ```
  cd backend && ./.venv/Scripts/python.exe -m api.demo_helix
  ```
- **Run the tests** (proof of correctness):
  ```
  cd backend && ./.venv/Scripts/python.exe -m pytest -q     # 43 passing
  ```

---

## Part 10 — Troubleshooting

| Symptom | Fix |
|---|---|
| Red **`api offline`** badge / top banner | Backend isn't running — start Terminal 1 (1.3) and refresh. |
| `Port 5173 is already in use` | An old app instance is running. Close it, or it's already serving — just open http://localhost:5173. |
| Sign-in fails with 400 | Password too short, or the email is already registered — use **Sign in** instead of Create account. |
| Reply is empty / `[rate limit]` | Groq free-tier throttling — wait a few seconds and retry; the demo uses the light `8b-instant` model to avoid this. |
| Deep Reasoning runs long | Keep the question short; it's tuned to converge in ~7s. Use **Kill** if needed. |
| Presence shows only me | Expected — the live WebSocket presence room isn't built yet. |
| Browser won't reach API | Make sure the app is on **:5173** (CORS only allows that origin). |

---

## What's NOT wired yet (so you're not surprised)
- **Live presence / see teammates in real time** (WebSocket room) — next backend task.
- **Server-side Steer** for Deep Reasoning over HTTP — engine supports it; API doesn't yet.
- **Server-enforced** auth/role checks on chat routes — the UI enforces roles; the
  server will enforce them once the routes are gated.
- **Tool-permission layer** for Deep Reasoning — future.
