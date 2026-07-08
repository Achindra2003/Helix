# Helix — Demo Presentation Script (who says what, what to show)

A segment-by-segment runbook for the live demo. Total target: **~10–12 minutes**
+ Q&A. Speakers are assigned by lane — swap freely.

- **A = Achindra** — AI engine, Deep Reasoning, frontend integration
- **M = Mansoor** — backend, auth & multi-tenancy, data model
- **R = Rajnish** — UI/UX, design system

> Pitch in one line: **"Helix is Git for your team's AI work — shared, branchable
> AI conversations, a reusable prompt library, and a self-halting Deep Reasoning mode."**
> Make the **fork** the moment everyone remembers; Deep Reasoning is the flashy bonus.

---

## 0. Pre-flight (do this BEFORE the panel walks in)

- [ ] Start it: `./frontend/run-demo.ps1` (backend :8000 + app :5173, opens browser).
- [ ] Confirm the auth screen shows a green **`api ✓ (groq)`** badge.
- [ ] **Pre-create one account + workspace** and **send 2–3 messages** in a
      conversation titled *"Retrieval chunking strategy"* so the workspace looks
      lived-in (don't start from a blank screen).
- [ ] Have a **second browser/incognito** logged in as a second member (optional,
      for the "team" feel) — or just mention teammates by name.
- [ ] Open `REQUIREMENTS-COVERAGE.md` in a tab for the architecture segment.
- [ ] **Fallback ready:** `demo_artifacts/demo_transcript.txt` and the narrated
      script (`Option A` in `HELIX-DEMO.md`) in case Wi-Fi/Groq is flaky.
- [ ] Decide who drives the keyboard (one person clicks; others narrate).

---

## 1. Hook & problem  ·  Speaker: **R**  ·  ~60s

**Say:**
> "Teams now do real work with AI — but that work is invisible and siloed. Everyone
> prompts alone in their own ChatGPT tab. There's no shared history, no way to branch
> an idea without losing the thread, and no way to reuse what worked. Helix fixes that:
> one shared, branchable workspace for a team's AI work — with a power mode for hard
> problems."

**Show:** the **auth screen** (the double-helix frontispiece). Note the live
`api ✓ (groq)` badge — "the backend is real and connected."

---

## 2. Sign in → workspace → roles  ·  Speaker: **M**  ·  ~90s  ·  *proves FR-1, FR-2, FR-3*

**Say:**
> "Helix is multi-tenant. You log in with a real account — hashed credentials, JWT.
> A **workspace** is the tenant boundary; nothing crosses it. Members have roles —
> Owner, Collaborator, Observer — and every action is checked against a policy table."

**Show / click:**
1. Sign in → land on the **workspace picker**; open the pre-made workspace.
2. Rail → **TEAM**: the members list, **+ Invite** (copy an invite link), and the
   **Permission Matrix** ("policy as data").
3. Top-right **role switch** → flip to **Observer**: the whole workspace dims and
   the composer/fork/escalate disappear. "Role is legible at a glance, and the UI
   re-skins itself." Flip back to **Owner**.

---

## 3. Shared, streaming conversation  ·  Speaker: **A**  ·  ~90s  ·  *proves FR-4, FR-8*

**Say:**
> "This is a shared conversation — any teammate sees it. Watch the reply stream in
> live, token by token, from Groq. The key thing: the assistant sees the *whole
> shared thread*, not just my last line."

**Show / click:**
1. Open the seeded conversation; type a follow-up that depends on earlier context
   (e.g. *"Given that, which option is simplest to ship?"*) → watch it **stream**.
2. Point out: author attribution, the **☁ groq** provider label, "shared" badge.
3. Mention: **+ New conversation** lets you pick **Shared** or **Private**.

---

## 4. Fork & branch — THE idea  ·  Speaker: **A**  ·  ~2 min  ·  *proves FR-6*

**Say:**
> "Here's the Git moment. I can **fork** this conversation at any point. The new branch
> *inherits* the shared context up to the fork, then evolves on its own — and the two
> branches never leak into each other. Explore a risky idea on a branch without
> wrecking the main thread."

**Show / click:**
1. Hover a message → **fork here** (or the **Fork** button); name it *"semantic-split"*.
2. The **branch lineage** sidebar shows main → the new branch; the new branch opens
   with the inherited history.
3. Send a message on the fork; switch back to **main** — "main never saw that."
4. Land the line: **"This is the novelty — branchable team conversations."**

---

## 5. Shared prompt library  ·  Speaker: **R**  ·  ~60s  ·  *proves FR-7*

**Say:**
> "A team's best prompts are an asset. The library makes them reusable — save, tag,
> search, and drop a winning prompt straight into any conversation."

**Show / click:**
1. Rail → **LIBR**: search a prompt, point out tags.
2. Click **Insert →** on one → it jumps back to the conversation and **runs that
   prompt as a turn**.

---

## 6. Deep Reasoning — the power mode  ·  Speaker: **A**  ·  ~2.5 min  ·  *proves FR-9, FR-10, FR-11, FR-12, NFR-6*

**Say:**
> "For a hard question, escalate to **Deep Reasoning** — a recursive engine that
> reasons, reflects, and synthesizes in a loop. Crucially it's *self-halting*: it
> stops when the answer stabilizes, not when it runs out of budget. And you stay in
> control — there's a kill switch and a live budget meter so it can never run away."

**Show / click:**
1. Type a genuinely hard question (e.g. *"Monolith or microservices for a 3-person
   startup?"*) → click **⟳ Deep Reasoning**.
2. Narrate the **right-hand monitor** as it runs:
   - the **topology** lighting up reason → reflect → synthesize,
   - the **energy** and **budget** meters, **depth / loop-guard / stability**,
   - the live **step trace**.
3. It **converges** (~7s) — point to **`converged`** and the crystallized answer.
   "It decided it was done."
4. Run it again and hit **◼ Kill switch** mid-flight → "stopped on command."
5. Note honestly: *Steer (pause → inject guidance → resume) is built into the engine;
   wiring it through the live API is the next step.*

---

## 7. History, replay & export  ·  Speaker: **A** (or M)  ·  ~45s  ·  *proves FR-13*

**Say:** "Everything's persisted and server-ordered. Any branch can be replayed
step by step, and exported."

**Show / click:** the conversation header → **replay** scrubber (step through the
thread), then **↓ md** / **↓ json** to download.

---

## 8. Under the hood + requirements coverage  ·  Speaker: **M**  ·  ~90s

**Say:**
> "Architecture: a FastAPI backend with a pluggable LLM provider (Groq or local
> Ollama by config), an append-only message tree that makes forks O(1), a durable
> store that runs on SQLite in dev and Postgres in prod, and a React + TypeScript
> frontend streaming over SSE. The Deep Reasoning engine is a separate recursive
> graph behind one clean interface."

**Show:** `REQUIREMENTS-COVERAGE.md` — "Up to this milestone: **10 of 14 functional
requirements fully delivered**, the rest partial or in progress." Scroll the matrix.

---

## 9. What's next (honest roadmap)  ·  Speaker: **M**  ·  ~45s

**Say:**
> "Remaining work is one backend lane, and the frontend already has the seams for it:
> (1) enforce auth/tenancy on the chat routes, (2) WebSocket presence + live-watch so
> you see teammates typing in real time, (3) server-side steer for Deep Reasoning,
> (4) a tool-permission layer. Then containerise and deploy."

---

## 10. Close  ·  Speaker: **R**  ·  ~30s

**Say:** "Helix turns scattered, throwaway AI chats into shared, branchable, reusable
team knowledge — with a reasoning mode you can actually trust and control. Thank you."

---

## NEW BEAT (added July 8, `ui-standout`) — Cited knowledge base: upload → grounded answer
*Slot it after the fork segment. Speaker: **R** · ~90s · proves the RAG lane (P1+P2)*

**Say:**
> "One more thing no competitor shows in one product: give the workspace a memory.
> I upload our spec once — for the whole team, no per-chat attach — and from then on,
> any question that touches it gets an answer *grounded on the document, with
> citations*. And because conversations are shared, my teammate watches those
> citations appear live in their browser."

**Show / click:**
1. Rail → **DOCS**: drag a small `.md` spec in → chip flips *⟳ processing* →
   *✓ ready* with a chunk count ("ingested: chunked and embedded, server-side").
2. Try the **knowledge-base search box** with a phrase from the doc — ranked
   chunks with relevance scores. "This is the exact ranking chat grounding uses."
3. Back to **CHAT**: ask a question that shares real terms with the doc → the
   reply streams in wearing **⌘ file.md §n** chips; hover one — the tooltip is
   the grounded excerpt. In the **second browser**, the same chips appear on the
   watcher's copy of the turn.
4. Ask something unrelated → **no chips**. Say why out loud: *"an unrelated
   question must not drag the knowledge base into every prompt — that's the
   relevance gate, not a bug."*

**Also worth flashing (P3, if time):** start a Deep Reasoning run, **reload the
page mid-run** — the monitor reattaches and the answer still lands ("the run
lives on the server now; closing the tab doesn't kill it — the **Stop** button
does").

---

## Q&A — likely questions & who answers

- **"Is the AI real or scripted?"** (A) — fully live Groq; show the streaming again, or the network tab.
- **"How is a fork instant on a long conversation?"** (M/A) — branches are *pointers* into a shared node tree; we copy no history (O(1) write, O(depth) read).
- **"What stops Deep Reasoning running forever / costing a fortune?"** (A) — a compute-budget halting controller + convergence thresholds + the kill switch (FR-12, NFR-6).
- **"Can you swap the model / run offline?"** (M) — one provider interface; flip Groq↔Ollama in config, no code change (FR-8, NFR-9).
- **"Is data isolated between teams?"** (M) — every resource is workspace-scoped; production adds Postgres Row-Level Security (FR-2, NFR-2).
- **"Why does presence show only me?"** (M) — the WebSocket room is the next backend task; the UI seam is already in place.

---

## If the live demo breaks (fallback)

1. Stay calm — say "let me show the recorded run."
2. Open `demo_artifacts/demo_transcript.txt` (a captured end-to-end run), **or**
3. Run the narrated script: `cd backend && ./.venv/Scripts/python.exe -m api.demo_helix`
   (`Option A` in `HELIX-DEMO.md`) — same story, no UI dependency.
4. Backend tests as proof of correctness: `pytest -q` → 43 passing.

## Don't-click list (avoid dead ends on stage)
- Don't rely on **Steer** in the monitor (button is disabled — not wired over HTTP yet).
- Don't expect **live presence** of a second user (no WebSocket yet) — describe it instead.
- Keep Deep Reasoning questions **short**; the bounded config is tuned for a ~7s converge.
