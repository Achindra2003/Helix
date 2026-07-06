# Baton → Rajnish: finish the UI & frontend of Helix

**Date:** July 6, 2026 · **Branch:** `ui-standout` (build here; `main` is the
frozen 25%-presentation version — never commit to it) · **Backend state:**
the AI lane is complete and stable (177/177 tests, commits `351137c` →
`2e870e4`). The endpoints and event shapes below are **contracts** — they
will not change under you.

Read in this order: this file → `AI-LANE-CONTRACTS.md` §2 (your formal
contract) → `HELIX-AI-EXPLAINED.md` (how the engine behind the UI thinks).

---

## 0. Orientation in one paragraph

Helix is a **shared LLM workspace for teams**: shared/private conversations,
Git-style forking with context inheritance, a shared prompt library,
real-time presence (watch a teammate's turn stream in live), cross-thread
references, steerable Deep Reasoning, and — new this week — per-workspace
BYO API keys and a file knowledge base with cited grounding. The frontend
you're finishing is the product's face; the two moments no competitor can
show are *two browsers, one thread, tokens streaming into both* and *a deep
run being steered mid-flight*. Protect those.

## 1. Run it

```bash
# backend (from backend/, venv exists at .venv)
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
# frontend (from frontend/app/)
npm run dev        # vite on :5173, strict port
```

- No Groq key → chat works on the **stub** provider (echo); Deep Reasoning
  returns a clear 503. Key lives in `backend/.env` (`GROQ_API_KEY=…`,
  `LLM_PROVIDER=groq`) or per-workspace via TEAM → Provider (that panel is
  already built: `src/routes/ProviderPanel.tsx`).
- Backend tests: `./.venv/Scripts/python.exe -m pytest -q` (all hermetic).
- Your gate for every change: `npm run build` clean + a live click-through
  of the changed surface (two browsers for anything multiplayer).

## 2. What already exists (don't rebuild)

| Surface | Files | Status |
|---|---|---|
| Auth, workspace picker | `routes/AuthPage.tsx`, `WorkspacePicker.tsx` | done |
| Chat: threads, streaming, fork, references, export, replay | `routes/ChatView.tsx`, `components/chat/*` | done |
| Deep Reasoning monitor + steer | `components/monitor/DeepReasoningMonitor.tsx` | done (needs the §3 additions) |
| Map (branch tree + presence dots) | `routes/MapView.tsx` | done |
| Prompt library | `routes/LibraryView.tsx` | done |
| Members + roles + **Provider panel (BYO key)** | `routes/MembersView.tsx`, `ProviderPanel.tsx` | done |
| Realtime client (WS presence + run relay) | `lib/realtime.ts` | done |
| API client | `lib/api.ts` | extend here for everything new |

## 3. The work, in priority order

### P1 — Documents panel (the knowledge base gets a face)

The #1 product gap from `MARKET-VALIDATION.md` is closed server-side; it
needs UI. Suggested home: a **DOCS panel** — either a new rail route
(`/w/:wid/docs`) or a section on the TEAM page like ProviderPanel; your
call, keep it consistent with the shell.

Endpoints (all under `/api`, JWT header like every other call):

- `POST /api/workspaces/{wid}/documents` — multipart field `file`.
  Returns the document row immediately with `status: "processing"`.
  Poll list/detail until `ready` or `error` (413 = too big, 8 MB).
- `GET /api/workspaces/{wid}/documents` → `{items: [{id, filename, status,
  error, chunk_count, text_chars, size_bytes, author_id, created_at}]}`
- `DELETE /api/workspaces/{wid}/documents/{id}` — uploader or owner only.
- `POST /api/workspaces/{wid}/documents/search` `{query, k}` → ranked
  chunks `{items: [{document_id, filename, chunk_index, score, content}]}`
  — build a small "search the knowledge base" box with this.

Acceptance: upload a .md → chip shows *processing* → *ready* with chunk
count; a bad file (.png) shows its error reason inline; observer sees the
list but no upload button; delete asks once and the list updates.

### P2 — Grounding citation chips in chat

The backend now emits a `grounding` SSE frame **before the reply's tokens**
whenever workspace documents were relevant to a turn:

```jsonc
{"kind": "grounding", "items": [{
  "document_id": "…", "filename": "spec.md", "chunk_index": 2,
  "score": 0.41, "excerpt": "first 200 chars…"
}]}
```

Handle it in `ChatView`'s SSE else-if chain (it's currently ignored,
harmlessly) and render source chips on the assistant message — "⌘ spec.md
§3" style, tooltip = excerpt. Also arrives on the WS `run_event` relay so
watchers see the same chips. Acceptance: upload a doc, ask a related
question → chips appear; ask something unrelated → no chips (that's the
relevance gate working, not a bug).

### P3 — Deep-run resilience UI (the backend outlives the tab; the UI should know)

Deep runs now execute server-side. Every deep run's **first frame** is
`{"kind": "deep_run", "run_id": …}` (previously steerable-only). New
endpoints:

- `GET /conversations/deep/runs/{id}/stream?after=N` — replay events from
  seq N then follow live. **Reconnect path**: persist `{runId, seq}` of an
  in-flight run (count frames you've consumed) in component state /
  sessionStorage; on mount, if one exists, reattach instead of showing a
  dead monitor.
- `GET /conversations/deep/runs/{id}/status` → `{status, seq,
  queue_position}`; status ∈ queued|running|paused|done|error|killed.
- `POST /conversations/deep/runs/{id}/kill` — **closing the stream no
  longer stops a run.** The monitor needs an explicit Stop button (wire it
  here, Collaborator+).
- New frame `{"kind": "queued", "position": 1}` — render "queued behind a
  teammate's run" in the monitor instead of a silent stall.

Acceptance: start a deep run, reload the page mid-run → monitor reattaches
and the answer still lands; Stop halts it with `status: killed`; two
concurrent runs + a third shows the queue notice.

### P4 — Run history ("the team's reasoning archive")

Endpoints have existed since July 4 and have no face:

- `GET /conversations/{conversation_id}/deep/runs` — newest-first summaries
  (question, status, stop_reason, stability, confidence, tokens, duration).
- `GET /conversations/deep/runs/{run_id}/record` — full record incl. step
  trace, steer notes, **and now `model` + `provenance`** (which model/
  thresholds produced it — render it; it's the trust story).

Suggested: a "Runs" drawer on the conversation (or a tab in the monitor
panel) listing past runs; click → a read-only trace view (reuse the
monitor's step-rendering components).

### P5 — Polish pass (from LAUNCH-PLAN.md, in scope if time allows)

Keyless-workspace nudge already exists; add: empty states for docs/library,
a small-screen pass (the launch plan flags it), and verify react-markdown
never renders raw HTML (XSS audit item — it's safe by default; just don't
enable `rehype-raw`).

## 4. Design constraints (non-negotiable)

- **Light parchment** theme — *not* dark "Alchemical Noir". **Oxblood** is
  the primary-button fill; **gilt/gold is outline-only**, never a fill.
- **Scholarly motifs only** (manuscript, helix, astronomy). **No occult
  symbolism** — no pentagrams, alchemy sigils, hermetic marks (Christ
  University requirement; this already caused one full rework, don't repeat
  it).
- Match the existing voice: serif display for brand moments
  (`serif-d`), mono tags for system labels, CSS modules per route.

## 5. Ground rules

1. **Don't modify the backend.** The AI lane is contract-stable; if a
   contract seems wrong or missing, flag it to Achindra — don't patch around
   it in `api/`.
2. Unknown SSE/WS `kind`s must stay ignorable — the else-if pattern already
   guarantees this; keep it.
3. Commit per surface (P1, P2, …) to `ui-standout` with the build green, so
   the branch always demos.
4. The demo script is `HELIX-DEMO-SCRIPT.md`; after P1–P3, extend it with
   the upload→grounded-answer moment — it's the newest "no competitor shows
   this" beat (live multiplayer + cited knowledge base in one product).

## 6. If something behaves oddly

- Event/endpoint truth: `AI-LANE-CONTRACTS.md`, then the routers themselves
  (`backend/api/documents/router.py`, `backend/api/conversation/router.py`).
- "Why did the AI do that": `HELIX-AI-EXPLAINED.md`.
- A grounding chip missing on a clearly-related question usually means the
  relevance floor (`grounding_floor=0.15`) — test with questions that share
  real terms with the doc, and remember the answer to "why not always
  ground?" is: *an unrelated question must not drag the knowledge base into
  every prompt.*

Good luck — the backend will not move under you. Ship the face.
