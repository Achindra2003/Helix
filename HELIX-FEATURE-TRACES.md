# Helix — How Every Feature Works, End to End

A guided walk through the execution path of each feature: what the user does,
what code runs (with file references), where data lands, and what will change
as the remaining work ships. Written for someone who has never seen the
product.

**What Helix is, in one paragraph:** a shared LLM workspace for teams. A team
makes a *workspace*, invites members with roles, and talks to an AI together —
conversations can be branched like a git tree, replies stream in live for
everyone watching, uploaded documents ground answers with citations, and while
you type, Helix quietly checks whether a teammate already explored your
question. Two heavier modes sit on top: *Deep Reasoning* (a visible,
steerable, budgeted reasoning loop) and *Agent mode* (the AI may call tools —
but only tools the workspace owner allowed, with a human approving sensitive
calls). Every workspace brings its own LLM API key, so a hosted Helix never
spends the operator's money.

**The stack, so the traces make sense:** a React frontend
(`frontend/app/src/`) talks to a FastAPI backend (`backend/api/`) over three
channels — ordinary HTTP calls, **SSE** (Server-Sent Events: a one-way stream
the server pushes tokens down), and one **WebSocket** per workspace (two-way,
used for presence and live fan-out to teammates). Data persists in SQL
(SQLite for dev/self-host, Postgres-ready) via SQLAlchemy. The reasoning
engine (`backend/engine/`) is a vendored LangGraph-based module the API drives
through a narrow contract.

**The shared spine (read this once, it applies to every chat-like trace):**
every kind of reply — plain chat, deep reasoning, agent — flows through one
orchestrator, `engine.send` (`backend/api/conversation/engine.py`), with a
swappable "producer" as the brain (`producer.py`: *"one mount, two
producers"* — now three). A producer only emits content events (`Token`,
`Step`, `Grounding`…); `engine.send` brackets them with persistence events
(`UserNode`, `AssistantNode`, `Done`). So persistence, streaming, RBAC, and
realtime relay are written once and every mode inherits them.

---

## 1. Accounts & sign-in (FR-1)

**What you see:** a register/login screen; you stay signed in across reloads.

**The path today:**
1. The auth screen posts email + password to `/api/auth/register` or
   `/api/auth/login` (`backend/api/routers/auth.py`).
2. Passwords are stored bcrypt-hashed, never plain. A successful login mints a
   **JWT** (a signed token proving who you are) using the server's
   `jwt_secret` (`backend/api/security.py`).
3. The frontend keeps the token and sends it on every request; on reload it
   calls `/api/me` to rehydrate the session.
4. Every protected route resolves the user via `get_current_user`
   (`backend/api/deps.py`) — identity always comes from the token, never from
   client-supplied ids. Change-password and delete-account flows exist too.

**What will be:** Mansoor's P2 makes the server *refuse to boot* on the dev
`jwt_secret` and rate-limits signup (today nothing stops scripted account
creation). P4 adds password reset — the one auth flow a hosted instance can't
live without.

## 2. Workspaces, invites & roles (FR-2, FR-3)

**What you see:** a workspace picker, a TEAM panel with members, and invite
links that carry a role. An Observer can read but not write.

**The path today:**
1. Creating a workspace (`backend/api/routers/workspaces.py`) writes a
   `Workspace` row and an owner `Membership` (`backend/api/models.py`).
2. **+ Invite** creates a token link with a role and an expiry; whoever opens
   it and accepts gets a membership at that role. Invites can be listed and
   revoked.
3. Roles form a ladder — owner ⊃ collaborator ⊃ observer — enforced
   **server-side on every route**: reads need any membership, writes need
   Collaborator+, settings need owner. A non-member asking about any resource
   gets **404, not 403** — outsiders can't even confirm something exists.
4. The UI mirrors what the server enforces (an Observer's composer is
   read-only), but the server is the authority.

**What will be:** P2 adds the missing abuse caps — workspaces per user,
members per workspace, invite **max-uses** (expiry already exists). NFR-2's
Postgres Row-Level Security remains a hosted-deploy hardening step; today
isolation lives entirely (and completely) in the API layer.

## 3. Conversations & streaming chat (FR-4)

**What you see:** you create a conversation (**⊙ Shared** or **◍ Private**),
type a message, and the reply appears token by token.

**The path today:**
1. Send hits `POST /api/conversations/.../send`
   (`backend/api/conversation/router.py`) which returns an **SSE stream**.
2. The route checks membership + role, then calls `engine.send` with a
   `ChatProducer` (`producer.py:42`).
3. Before the model sees anything, the producer assembles context
   (`context.py`): the branch's ancestor history as real chat turns, any
   **referenced conversations** folded into the system frame, a semantic
   **recall block** of relevant elided turns (§11's substrate), and a
   **grounding block** from workspace documents (§9) — the latter two inside a
   `<quoted-context>` boundary so injection defenses apply (there is an
   adversarial regression suite for exactly this).
4. One streamed provider call runs (§7); each chunk is relayed to you as an
   SSE `Token` event, and simultaneously to teammates viewing the same shared
   thread via the workspace WebSocket (§4).
5. `engine.send` persists both turns through `DbStore`
   (`store.py`, behind a `ConversationStore` Protocol), which fires
   embedding-on-write for the new nodes (§11). Token usage lands in the
   ledger (§12). Private threads skip the room relay entirely — they never
   leave author + server.

**What will be:** P2 rate-limits the send route per user (the flood risk is
DB spam and WebSocket noise — the LLM cost is already the workspace's own
key). Nothing else changes; this path is contract-frozen.

## 4. Live multiplayer — presence & fan-out (FR-5)

**What you see:** a presence bar showing who's online; a teammate's reply
streaming into your open thread; new conversations and forks appearing with no
refresh.

**The path today:**
1. On entering a workspace the frontend opens
   `/ws/workspaces/{id}?token=<jwt>` (`backend/api/realtime.py` — the token
   rides a query param because browsers can't set WebSocket headers; it's
   verified exactly like a header).
2. The room is an in-process dict: joins/leaves broadcast the roster
   (deduplicated per user across tabs, including *which branch* each person is
   viewing — that powers the Map's presence dots and the "✒ … is asking
   Helix" hint).
3. HTTP routes call `realtime.broadcast(...)` when anything changes — a
   streaming turn, a new conversation, a fork, a saved prompt. The sender is
   excluded (their own SSE/response already carries the change); dead sockets
   are dropped without breaking the sender (NFR-7).

**What will be:** single-instance by design, and staying that way — the
documented seam is that `broadcast()`/`roster()` are the *only* two functions
above the room dict, so a Redis pub/sub swap touches one module if
multi-instance ever matters (P5, deliberately deferred). This is also why the
GCP hosting decision is one always-on VM, not Cloud Run: scale-to-zero would
kill these in-process rooms.

## 5. Forking & the branch tree, Map, replay & export (FR-6, FR-13)

**What you see:** hover any message → **fork here**; a Branch-lineage sidebar;
a workspace **Map** of the whole tree with live presence dots; a replay
scrubber; **↓ md / ↓ json** export.

**The path today:**
1. A fork (`POST .../fork`) creates a `BranchRow` whose parent pointer is the
   forked-from node (`conversation/models.py`). Nothing is copied — history is
   *derived* by walking the ancestor spine, so a fork inherits exactly the
   ancestor context and nothing from sibling branches (`context.py`).
2. The lineage sidebar and the Map (`conversation/map.py`) render that
   parent→child topology; the Map overlays who is viewing which branch, from
   the room roster (§4).
3. Replay is client-side: the scrubber steps through the already-fetched
   node sequence — no server round-trips.
4. Export streams the thread as Markdown or JSON through an authenticated
   download route — same RBAC as reading.

**What will be:** nothing in Mansoor's lane touches this. It is the feature
most purely "done."

## 6. Shared prompt library (FR-7)

**What you see:** a LIBR panel — save a prompt with tags, search it, **Insert
→** runs it as a turn; teammates' saves appear live.

**The path today:**
1. CRUD routes in `backend/api/prompts/router.py`, rows via
   `prompts/store.py`; membership-gated like everything else.
2. A save broadcasts to the room (§4), so the library updates live for
   everyone.
3. **Insert** doesn't paste text client-side — it runs the prompt through the
   same send path (§3), so the turn is persisted, streamed, and relayed
   normally.

**What will be:** untouched by the remaining work.

## 7. The provider layer & BYO keys (FR-8, FR-16)

**What you see:** the UI shows the active provider (`☉ groq`); a workspace
owner can open TEAM → Provider, paste their own API key, pick models, and
**Test connection**.

**The path today:**
1. All model calls go through one `LLMProvider` interface
   (`backend/api/providers/base.py`) with Groq, Ollama,
   OpenAI-compatible, and a stub (for tests) behind it.
2. Which provider a call uses is decided per workspace by one pure function:
   `resolve()` in `backend/api/provider_settings.py`. Workspace settings win;
   the server `.env` is the fallback. A hosted instance ships with **no
   fallback key**, so a workspace can never spend the operator's money — this
   is the economic design of the whole hosted track.
3. Workspace keys are encrypted at rest with a Fernet key derived from the
   server secret; the key never appears in any API response. Rotating the
   server secret deliberately invalidates stored keys — the failure mode is
   "re-paste your key," never a leak.
4. Every call is wrapped by `providers/resilient.py`: retry, circuit breaker,
   and safe fallback, so a flaky provider degrades a reply instead of
   crashing a run. Chat and Deep Reasoning use independently configured
   models (fast 8B for chat, 70B for deep runs, on the current Groq setup).

**What will be:** P2's boot-refusal on the dev secret protects exactly the
secret this encryption hangs off. `.env.example` (P1) documents every knob.

## 8. Deep Reasoning — the run, the monitor, steering, budget (FR-9…FR-12)

**What you see:** toggle **⟳ Deep Reasoning** and ask something hard. A right
panel lights up: a topology strip stepping node by node, energy and budget
meters, a live trace of thoughts. You can **Stop** it, or run **⟂ guided**
mode where it pauses between cycles and lets any collaborator inject
guidance. Closing the tab doesn't kill the run.

**The path today:**
1. The send route swaps in the second producer: `DeepReasoningProducer`
   (`conversation/deep_reasoning.py`) driving the vendored Ouroboros
   LangGraph (`backend/engine/`). The graph loops reason → reflect →
   synthesize and halts on **semantic convergence** (successive syntheses stop
   changing, measured with MiniLM embeddings) or on budget. This claim is
   *measured*, not asserted — `backend/evals/FINDINGS.md`, 8/8 hard
   questions, 3 arms: the controller converged 8/8 while blind fixed
   iteration scored worst at 2× the tokens.
2. The producer maps graph events to the shared contract: `Step` for each
   transition (thought, stability, confidence…), `Budget` for the meter,
   `Waiting` when paused for steer, and `Token`s **only for the final
   answer** — so the persisted message is the answer, not the thought stream.
3. Crucially, the run does **not** live inside your HTTP request
   (`conversation/runs.py`): it executes in a server-side task appending to a
   per-run event log. Your SSE stream is just a *subscriber* — reconnect with
   `?after=N` and it replays what you missed, then follows live. Teammates
   watching the shared branch get the trace relayed via the room. A
   per-workspace concurrency cap queues excess runs (`queued` is a visible
   event) to protect the workspace's own rate limits.
4. **Stop** is `POST .../kill` — a server-side halt, not an aborted stream.
   **Guided** mode pauses at a LangGraph checkpoint between cycles; steer
   text resumes the run over HTTP from that checkpoint; abandoned pauses
   expire after 30 minutes. Budget is enforced twice: the engine's
   compute-budget halt plus a wall-clock deadline per segment (a rate-limited
   provider can't stretch a run forever).
5. Each finished run persists a durable `DeepRunRow` with provenance (model,
   thresholds) — the Run history drawer reads these.

**What will be:** the one honest gap — run handles are in-process, so a
*process restart* (not a closed tab) still loses an in-flight run; the
durable row keeps the evidence. The fix is documented as P5: the LangGraph
sqlite checkpointer (the parameter already exists on the graph builders) plus
a persisted run registry. It moved up in value because it also covers agent
runs paused for approval (§10). P2 rate-limits the deep route.

## 9. File grounding — the workspace knowledge base (FR-15)

**What you see:** upload files in the DOCS rail → they become "ready" with a
chunk count. Later, answers that relate to those files carry citation chips
("⌘ spec.md §3"). Unrelated questions get no chips — that's the relevance
gate working, not a bug.

**The path today:**
1. Upload (`backend/api/documents/router.py`) → server-side hygiene (8 MB
   cap, extension allowlist, per-workspace count cap) → text extraction
   (`documents/service.py`: PDFs via pypdf, code/text decoded directly —
   the original bytes are *not* kept, only extracted text).
2. The text is chunked and embedded on the same shared embedder as
   everything else (§11), chunks stored as ordinary DB rows
   (`DocumentChunkRow`) with packed float32 vectors — deliberately no vector
   database at this scale (~10⁵ chunks before that decision is revisited).
3. At send time — chat *and* deep runs — the producer's `grounder` asks
   `DocumentIndex.grounding_block()` for chunks relevant to the current turn.
   Below the measured relevance floor (0.20), nothing is injected. Above it,
   chunks enter the prompt inside the `<quoted-context>` boundary (injection
   defenses apply to documents automatically) and a `Grounding` event carries
   the citation metadata to the UI, which renders the chips.

**What will be:** originals-as-blobs is the labeled P5 seam (re-upload =
re-ingest today; nothing reads raw bytes after ingest). If that ever ships on
the GCP deployment, the free 5 GB Cloud Storage bucket is where originals
would go — it has no role before then.

## 10. Agent mode — governed tools with human approval (FR-14)

**What you see:** toggle **⚒ Agent** and ask something that needs looking up.
The reply carries a live *tool ledger* — each call, its arguments, its
status. If the agent wants to search the web, a banner appears above the
composer and the run *waits* until a member approves or denies.

**The path today:**
1. The third producer: `AgentProducer` over a LangGraph tool loop
   (`backend/api/tools/agent.py`).
2. Three policy layers, deliberately separate (`tools/__init__.py` is the
   design doc):
   **Catalog** (`tools/builtin.py`) — what exists: search the knowledge base
   (§9's index), search past conversations (§11's index — inheriting its
   visibility guarantees), web search via Tavily. A tool that can't work in
   this deployment (no Tavily key) is *visibly unavailable*, not silently
   missing.
   **Allowlist** — what this workspace permits, owner-managed
   (`WorkspaceSettings.tool_allowlist`, TEAM → Agent tools; default:
   the two internal search tools). Enforced **by binding, not refusal**: an
   un-allowed tool is never offered to the model at all — a door the model
   never learns about, not a locked one.
   **Approval** — sensitive tools (anything leaving the workspace, i.e. web
   search) pause the run at a LangGraph `interrupt_before` checkpoint before
   *every* call until a human verdict arrives over HTTP.
3. Tool calls and results stream as ledger events over the same SSE + room
   relay as everything else, so watchers see the agent work live.

**What will be:** the approval pause lives in a MemorySaver checkpoint, so a
server restart loses a run that's waiting on a human — flagged in Mansoor's
baton as "the first bug report a real self-hoster will file" (P5, same fix as
§8). P2 rate-limits the agent routes with the note that one run fans out into
multiple LLM + tool calls. `TAVILY_API_KEY` joins `.env.example` in P1.

## 11. Workspace search & proactive resurfacing (the identity feature)

**What you see:** two surfaces of one substrate. A search overlay finds any
message you're allowed to see. And while you type a question — unprompted — a
strip may appear over the composer: **"✦ explored before —"** with up to
three chips linking to where *you, Helix, or a teammate* already worked on
this. Click one and you're in that thread. This is the product's thesis
("nobody re-asks what a colleague solved") made visible at the exact moment
it matters.

**The path today (write side — how the memory builds):**
1. Every persisted node triggers a fire-and-forget embed
   (`router.py:86` wires `DbStore(on_node=_embeddings.ensure_soon)`).
2. `EmbeddingIndex.ensure()` (`conversation/embeddings.py`) embeds each
   immutable node exactly once — MiniLM in a worker thread, lexical fallback
   without the neural deps — into `NodeEmbeddingRow`: packed float32 bytes in
   an ordinary column, identical on SQLite and Postgres. Rows are versioned
   by embedder name, so upgrading the embedder is a lazy re-embed, never a
   migration. A lost background task is harmless: retrieval backfills.

**The path today (read side — the strip):**
3. Keystrokes route through `onDraftChange` (`ChatView.tsx:229`): under 18
   chars clears the strip; a 700 ms debounce absorbs typing; a sequence
   counter discards superseded responses.
4. `POST /api/workspaces/{wid}/search` (`routers/workspaces.py:330`) — JWT,
   membership gate, then `search_workspace()` (`embeddings.py:214`): one SQL
   join Node→Branch→Conversation carrying the *same visibility clause as
   thread listing*, so a private thread can never resurface for a non-author.
   Cosine similarity runs in plain Python over the candidates; top-k above a
   0.15 floor.
5. The client is stricter than the server: it drops the thread currently on
   screen, raises the floor to 0.33 (this surface is *unsolicited* — a wrong
   chip is noise, unlike a requested search), keeps one chip per
   conversation, max three. A × mutes the strip for this question.
6. The same endpoint powers the search overlay and the agent's
   `search_conversations` tool — three surfaces, one guarantee set. The same
   substrate also serves chat's semantic recall block (§3) via
   `recall_block()`, which degrades to recency on any failure — recall is an
   enhancement, never a failed send.

**What will be:** P2 should rate-limit this route (it's the chattiest
authenticated endpoint — one embed per pause-in-typing). P3's Alembic
baseline must capture `NodeEmbeddingRow`. P4's seeded example workspace
exists partly so this strip has something to show a brand-new user. And one
decision to make knowingly: on a slim deployment image without the neural
deps, resurfacing quality silently degrades to the lexical fallback — for the
identity feature, that tradeoff should be chosen, not discovered.

## 12. Usage telemetry (supports FR-12)

**What you see:** a per-workspace usage view of model calls.

**The path today:** every provider call reports (model, token usage, latency)
through a `UsageSink` the router binds per workspace
(`conversation/router.py:72`); rows land in `LlmCallRow`
(`backend/api/telemetry.py`); `GET .../usage` serves the ledger. OpenTelemetry
spans wrap LLM calls and retrieval for tracing.

**What will be:** P3 must include `api/telemetry.py` in the Alembic baseline
(the sixth model file — called out in Mansoor's baton because his July 6 copy
predated it). Per-workspace rate *metering* surfaced in the UI is the one
FR-12 remainder, unscheduled.

---

## The road from here (all features at once)

The product lane is finished: 16/16 FRs, 261 hermetic backend tests (stub
provider + throwaway SQLite — no keys, no network), frontend typechecks
clean, and a 10-step scripted browser click-through
(`frontend/app/e2e/smoke.mjs`) that drives register → streamed chat → upload
→ cited grounding → resurfacing → agent run with approval → deep monitor →
map against a real provider.

What turns it from "finished" into "launchable" is the infra lane
(`BATON-MANSOOR.md`):

- **P1 — the install.** One production container serving the built frontend
  from FastAPI; `git clone && docker compose up` → register at
  `localhost:8000`. CI runs the hermetic suite; images publish to a registry.
- **P2 — secure-by-default.** Refuse to boot on the dev secret; rate limits
  on signup/send/deep/agent/search; caps on workspaces, members, invite uses.
- **P3 — Alembic baseline** over all six model files, so a hosted instance
  can upgrade without losing data (self-hosters keep zero-infra
  `create_all`).
- **P4 — the hosted instance.** Postgres + backups, password reset,
  monitoring, a seeded example workspace. Decided July 18: it runs at $0 on
  one GCP Always-Free e2-micro VM running the *same* compose file as
  self-host — Cloud Run was rejected because scale-to-zero kills the
  in-process rooms and run registry that Helix's single-instance design
  deliberately embraces.

After that, only human items remain: a license file (the legal blocker for
anyone adopting the repo), a recorded demo GIF, and the first real teams —
whose usage is the only test of the social claims (resurfacing, shared
steering) that no suite can verify.
