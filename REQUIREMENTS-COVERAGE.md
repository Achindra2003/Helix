# Helix — Requirements Coverage (traceability)

Maps every requirement in `helix-srs.md` §3 to its current status and **where to
see it** in the running product. Use this as the demo script and the "what's done"
record for the milestone.

**Legend:** ✅ delivered & demonstrable · 🟡 partial · ⬜ not started.

Run it: backend `uvicorn api.main:app` + `cd frontend/app && npm run dev` →
sign in → create/pick a workspace. (Or `./frontend/run-demo.ps1`.)

---

## Functional requirements

| # | Requirement | Status | Where to see it |
|---|---|:--:|---|
| **FR-1** | Auth & accounts (register/login, hashed creds, JWT) | ✅ | Auth screen: create account / sign in; token persists across reload (`/api/me` rehydrate). |
| **FR-2** | Workspaces & multi-tenancy (create, invite, isolation) | ✅ | Workspace picker → **New workspace**; **TEAM → + Invite** (now carries a role: collaborator or observer), **Join via invite** on the picker. Lists are workspace-scoped. |
| **FR-3** | RBAC (role per member, authorise every action) | ✅ | Enforced **server-side on every conversation/prompt route**: identity from the JWT (client ids ignored), reads need membership, writes need Collaborator+, private threads are author-only, non-membership reads as 404. UI mirrors it (Observer goes read-only). |
| **FR-4** | Shared & private conversations + token streaming | ✅ | **+** new conversation → choose **⊙ Shared / ◍ Private**; reply **streams token-by-token**; private threads never appear in others' lists, fetches, or the realtime room. |
| **FR-5** | Real-time sync & presence (WebSocket room) | ✅ | `/ws/workspaces/{id}` room: presence bar shows **who's online, live**; a teammate's turn on your open thread **streams in token-by-token**; new conversations/forks/prompts appear without refresh. Open two browsers to see it. |
| **FR-6** | Fork & branch tree (inherit context, interactive tree) | ✅ | Hover a message → **fork here**, or the **Fork** button; **Branch lineage** sidebar shows parent→child, active highlighted, click to open. Fork inherits ancestor context, siblings stay isolated. |
| **FR-7** | Shared prompt library (save, tag, search, insert) | ✅ | **LIBR**: search, tags, **+ Save prompt**, **Insert →** (runs the prompt as a turn); teammates' saves appear live. |
| **FR-8** | LLM provider abstraction (Groq/Ollama by config) | ✅ | Backend provider interface; UI shows the active provider (`☉ groq`). Swap via `backend/.env`. Deep Reasoning uses its own `DEEP_REASONING_MODEL` (70B) independent of chat. |
| **FR-9** | Deep Reasoning mode (recursive, step events) | ✅ | Composer **⟳ Deep Reasoning** → recursive reason→reflect→synthesize on the 70B model; halts on **semantic convergence** (MiniLM embeddings) or budget; each step emits node/depth/energy/thought/synthesis/readings. The run itself now executes **server-side** — closing the tab no longer kills it (reconnect on reload; explicit **Stop** button). |
| **FR-10** | Deep Reasoning monitor (trace, topology, meters) | ✅ | Right panel: **topology strip** lighting node-by-node, **energy + budget** meters, **depth / loop-guard / stability / confidence / tokens**, live **step trace**, a **queue indicator** when a workspace's concurrency cap is hit, and a **Run history** drawer (past runs incl. model + provenance). Teammates watching the same shared branch see the trace live too. |
| **FR-11** | Run control — kill & steer | ✅ | **Stop** halts a run server-side (`POST .../kill`) — no longer just an aborted local stream. **⟂ guided** toggle → the run **pauses between reasoning cycles**; the monitor opens a steer box — inject guidance (any Collaborator can) or continue as-is; the run resumes over HTTP from its checkpoint. |
| **FR-12** | Budget meter & guardrails | ✅ | Budget meter (% of cap) + the engine's **compute-budget halt** + a **wall-clock deadline** per run segment (a rate-limited provider can no longer stretch a run indefinitely). *Per-workspace rate metering not yet surfaced.* |
| **FR-13** | History, replay & export (JSON/Markdown) | ✅ | Conversation header: **replay** scrubber (step through the thread), **↓ md / ↓ json** export (authenticated download). |
| **FR-14** | Permission layer (tool allowlist + approval) | ✅ | Composer **⚒ Agent** → a LangGraph tool loop (search the knowledge base, past conversations, or the web) with three policy layers enforced **by binding, not refusal**: a catalog with availability (web search greys out without a server Tavily key), an **owner-governed allowlist** (TEAM → Agent tools), and **human-in-the-loop approval** — sensitive calls checkpoint-pause the run (`interrupt_before`) until a member approves or denies from the banner above the composer. Each reply carries a live **tool ledger** (call, args, status), relayed to watchers too. Un-allowed tools are never offered to the model at all. |
| **FR-15** *(new)* | File grounding — workspace knowledge base (RAG) | ✅ | Rail → **DOCS**: upload → chunked + embedded server-side → **ready** with a chunk count; a search box ranks chunks by relevance. Chat **and** Deep Reasoning replies ground on relevant chunks automatically (workspace-wide, no per-conversation attach) with **citation chips** ("⌘ spec.md §3") when relevance clears a measured floor — silently absent on unrelated questions, which is the relevance gate working, not a bug. Closes the #1 gap named in `MARKET-VALIDATION.md`. |
| **FR-16** *(new)* | Per-workspace provider settings (BYO API key) | ✅ | TEAM → **Provider** panel (owner-only): pick provider, paste an encrypted key, pick models, **Test connection**. Server-wide `.env` values remain the fallback (self-host needs nothing new); a hosted instance ships with no fallback key so a workspace can never spend the operator's key. Retry/circuit-breaker/safe-fallback wrap every call. |

## Non-functional requirements

| # | Requirement | Status | Notes |
|---|---|:--:|---|
| **NFR-1** | Performance & latency (<200 ms realtime) | ✅ | Token streaming is immediate; room fan-out is in-process (sub-ms relay per event). |
| **NFR-2** | Multi-tenancy & isolation (RLS) | 🟡 | Tenancy enforced in the API layer on every route (membership-gated, 404 on probing). PostgreSQL Row-Level Security remains a prod-deploy step. |
| **NFR-3** | Cost efficiency (budget halt; Groq/Ollama) | ✅ | Compute-budget halting + provider switch (hosted/local) + dead web-research short-circuit (no wasted LLM calls when search has no backend). |
| **NFR-4** | Scalability (in-memory rooms; Redis optional) | 🟡 | In-process rooms behind a two-function seam (`broadcast`/`roster`) — a Redis pub/sub swap touches one module. |
| **NFR-5** | Security (JWT + RBAC; no cross-tenant) | ✅ | JWT + server-side RBAC on **all** routes (auth/workspaces/conversations/prompts/WS). Unauthenticated `/chat/stream` stub removed. |
| **NFR-6** | Reliability & interruptibility | ✅ | Kill switch + budget/depth halt; engine catches mid-stream failure → clean `complete(error)` (no torn stream); paused guided runs expire after 30 min. |
| **NFR-7** | Streaming & backpressure (fan-out to N) | ✅ | SSE to the author + WS relay to every room member; dead sockets are dropped without breaking the sender. |
| **NFR-8** | Privacy (minimal data) | ✅ | Only email + conversation content; no biometric/audio/video. Private threads never enter the room. |
| **NFR-9** | Portability (containerised; pluggable providers) | 🟡 | Provider interface ✅; Dockerfile + compose exist; containerised run not exercised this milestone. |

---

## Scorecard

- **Functional:** 16 of 16 fully delivered (14 original + 2 added this
  milestone).
- **Non-functional:** NFR-1,3,5,6,7,8 delivered; NFR-2,4,9 partial.

**Verification:** backend `pytest -q` → **257 passed** (hermetic: stub provider
+ throwaway SQLite, no network/keys required; includes RBAC-gating, WebSocket
room, guided-steer, provider resilience, durable deep runs, file grounding,
deep-run grounding, the agent tool loop with its approval gate and allowlist
policy, and an adversarial injection-regression corpus);
frontend `npm run build` typechecks clean; a scripted live end-to-end run
(2 users over real HTTP + WS + Groq) passes 15/15 checks: presence, live token
fan-out, fork, references, guided steer to convergence, observer gating,
authed export.
