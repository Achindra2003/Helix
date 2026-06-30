# Helix — Requirements Coverage (traceability)

Maps every requirement in `helix-srs.md` §3 to its current status and **where to
see it** in the running product. Use this as the demo script and the "what's done"
record for the milestone.

**Legend:** ✅ delivered & demonstrable · 🟡 partial · 🔌 frontend-ready, awaits a
backend seam · ⬜ not started.

Run it: `./frontend/run-demo.ps1` → sign in → create/pick a workspace.

---

## Functional requirements

| # | Requirement | Status | Where to see it |
|---|---|:--:|---|
| **FR-1** | Auth & accounts (register/login, hashed creds, JWT) | ✅ | Auth screen: create account / sign in; token persists across reload (`/api/me` rehydrate). |
| **FR-2** | Workspaces & multi-tenancy (create, invite, isolation) | ✅ | Workspace picker → **New workspace**; **TEAM → + Invite** (copy token), **Join via invite** on the picker. Lists are workspace-scoped. |
| **FR-3** | RBAC (role per member, authorise every action) | ✅ client / 🟡 server | **TEAM**: members + **Permission Matrix**; top-right **role switch** re-skins the workspace — Observer goes read-only (composer, fork, escalate hidden). *Server-side gating on chat routes pending (Mansoor).* |
| **FR-4** | Shared & private conversations + token streaming | ✅ | **+** new conversation → choose **⊙ Shared / ◍ Private**; reply **streams token-by-token**; visibility shown in list + header. |
| **FR-5** | Real-time sync & presence (WebSocket room) | 🔌 | Append-only ordered log (server `seq`) ✅; presence bar shows "you" via a `usePresence` seam. *WebSocket room not built yet — lights up with no UI change when it lands.* |
| **FR-6** | Fork & branch tree (inherit context, interactive tree) | ✅ | Hover a message → **fork here**, or the **Fork** button; **Branch lineage** sidebar shows parent→child, active highlighted, click to open. Fork inherits ancestor context, siblings stay isolated. |
| **FR-7** | Shared prompt library (save, tag, search, insert) | ✅ | **LIBR**: search, tags, **+ Save prompt**, **Insert →** (runs the prompt as a turn in the conversation). |
| **FR-8** | LLM provider abstraction (Groq/Ollama by config) | ✅ | Backend provider interface; UI shows the active provider on the auth badge and composer (`☉ groq`). Swap via `backend/.env`. |
| **FR-9** | Deep Reasoning mode (recursive, step events) | ✅ | Composer **⟳ Deep Reasoning** → recursive reason→reflect→synthesize; converges or hits budget; each step emits node/depth/energy/thought/synthesis/readings. |
| **FR-10** | Deep Reasoning monitor (trace, topology, meters) | ✅ | Right panel: **topology strip** lighting node-by-node, **energy + budget** meters, **depth / loop-guard / stability / confidence / tokens**, live **step trace**. |
| **FR-11** | Run control — kill & steer | 🟡 | **Kill switch** halts the run ✅. **Steer** is shown but disabled (needs server-side run control over HTTP); steer→resume is proven at engine level in `demo_helix.py`. |
| **FR-12** | Budget meter & guardrails | ✅ | Budget meter (% of cap) + the engine's **compute-budget halt** (run converges/bounded, ~7s). *Per-workspace rate metering not yet surfaced.* |
| **FR-13** | History, replay & export (JSON/Markdown) | ✅ | Conversation header: **replay** scrubber (step through the thread), **↓ md / ↓ json** export. |
| **FR-14** | Permission layer (tool allowlist + approval) | ⬜ | Future enhancement; not built. |

## Non-functional requirements

| # | Requirement | Status | Notes |
|---|---|:--:|---|
| **NFR-1** | Performance & latency (<200 ms realtime) | 🔌 | Token streaming is immediate; realtime fan-out latency applies once the WebSocket room exists. |
| **NFR-2** | Multi-tenancy & isolation (RLS) | 🟡 | Workspace-scoped queries on dev SQLite; PostgreSQL Row-Level Security is a prod-deploy step. |
| **NFR-3** | Cost efficiency (budget halt; Groq/Ollama) | ✅ | Compute-budget halting + provider switch (hosted/local). |
| **NFR-4** | Scalability (in-memory rooms; Redis optional) | ⬜ | Depends on the WebSocket room (FR-5). |
| **NFR-5** | Security (JWT + RBAC; no cross-tenant) | 🟡 | JWT + RBAC on auth/workspaces/members/prompts; conversation-route gating pending. |
| **NFR-6** | Reliability & interruptibility | ✅ | Kill switch + budget/depth halt; engine catches mid-stream failure → clean `complete(error)` (no torn stream). |
| **NFR-7** | Streaming & backpressure (fan-out to N) | 🔌 | Single-client streaming is solid; N-client fan-out arrives with the WebSocket room. |
| **NFR-8** | Privacy (minimal data) | ✅ | Only email + conversation content; no biometric/audio/video. |
| **NFR-9** | Portability (containerised; pluggable providers) | 🟡 | Provider interface ✅; containerisation intentionally deferred (light-early setup). |

---

## Scorecard (up to this point)

- **Functional:** 10 of 14 fully delivered (FR-1,2,4,6,7,8,9,10,12,13); FR-3 & FR-11
  partial; FR-5 a frontend-ready seam; FR-14 future.
- **Non-functional:** NFR-3,6,8 delivered; NFR-2,5,9 partial; NFR-1,7 seam; NFR-4 pending.

**The four open items are one backend lane** (Mansoor's), and the frontend is already
built to absorb them with no rework:
1. Auth-gate + enforce tenancy on conversation/prompt routes (closes FR-3 server-side, NFR-5).
2. WebSocket presence + live broadcast (FR-5, NFR-1/4/7).
3. Server-side run control so steer→resume works over HTTP (FR-11).
4. (Future) tool allowlist + approval (FR-14).

**Verification:** backend `pytest -q` → 43 passed; frontend `npm run build` typechecks
clean; every ✅/🟡 row above is reachable in the running app.
