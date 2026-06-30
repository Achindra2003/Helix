# Baton — Helix (session handoff, through session #3)

> Read **§0 "What Helix is" first.** The recurring failure across sessions is
> re-drifting the product identity — over-elevating Deep Reasoning as "the
> novelty" and under-valuing the shared workspace. It happened again in session
> #3 and the user corrected it. The planning docs are right; defer to them.

---

## 0. What Helix is (LOCKED — do not re-derive)

- **Identity: a shared LLM workspace for a team.** "Git for your team's AI work."
  Everyday spine (~80% of usage): shared & private conversations, fork/branch any
  thread, a **shared, branchable context**, a shared prompt library, real-time
  presence, RBAC.
- **The novelty IS the shared workspace** — shared/branchable context + Git-style
  forking of a team's AI work (F2+F3+F5), not the deep-reasoning engine. (Session
  #3 drifted by calling the forkable workspace "just a chatbot that can fork" and
  elevating Ouroboros's convergence controller as "the real novelty." Wrong.)
- **Collaboration model = Git, not co-typed chat.** Each person has their own
  session; collaboration happens via visibility + live-watching + **fork** (fork a
  teammate's shared chat to inherit their context, continue in your own branch).
- **Deep Reasoning (Ouroboros) is a cuttable POWER FEATURE** (F6/F7), the bonus,
  plugged in later — NOT the identity.
- **The "AI portion" the project is built around = the CONVERSATION ENGINE**:
  `prompt → provider stream → persist as nodes`. **No LangChain/LangGraph in the
  core** — it's deliberately simple; the value lives in the *shared-context +
  fork* model and the clean seams, not in AI orchestration. LangGraph lives ONLY
  inside Ouroboros.
- **Architecture: "one mount, two producers."** One event contract; `ChatProducer`
  (now) and `DeepReasoningProducer` (Ouroboros) both emit it onto the same engine.

### The feature map (from `helix-analysis-phase.md`, F1–F9) and honest status
- **F1 Multi-tenant + RBAC** ✅ done (M1).
- **F2 Shared & private conversations** 🟡 engine streams+persists; **visibility
  NOT enforced** (conversation routes are open, no auth gating — Mansoor's lane).
- **F3 Fork & branch tree** ✅ backend done (O(1) fork, cross-branch history); no UI.
- **F4 Shared prompt library** ❌ not built.
- **F5 Real-time presence / live-watch** ❌ not built (Mansoor: in-memory WS rooms).
- **F6 Deep Reasoning mode** 🟡 integrated + one live run; **convergence not yet
  demonstrated** (the live run halted on `budget`, not `converged`).
- **F7 Monitor + kill/steer/budget** 🟡 kill ✅, budget events ✅, **steer NOT
  wired**; the monitor itself is UI.
- **F8 Provider layer** ✅ done (stub/groq/ollama).
- **F9 History / replay / export** 🟡 history endpoint done; **replay/export not built.**

---

## 1. Where the build actually is (DONE & GREEN: 22/22 tests)

Run tests: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`

**Foundation + M1 (done earlier):** monorepo, pluggable provider, `/health`,
SQLite-dev/Postgres-prod; auth (JWT/bcrypt), workspaces, memberships, RBAC
(owner⊃collaborator⊃observer; 404 non-member / 403 wrong-role), invites. Frontend
auth/workspace screens exist (old violet→cyan theme, NOT reskinned).

**E1 — conversation contracts + store (done):**
- `events.py` event contract (`Node`; chat: `UserNode/Token/AssistantNode/Done`;
  deep: `Step/Budget/Waiting/Complete`; `to_dict`/`to_sse`).
- `store.py`: `Conversation/Branch` dataclasses, `ConversationStore` Protocol,
  `InMemoryStore` **and** `DbStore` (SQLAlchemy async; same contract; per-branch
  `seq = head.seq+1`; O(1) fork + cross-branch history walk = algorithm A1).
- `models.py` ORM: `ConversationRow/BranchRow/NodeRow` (registered in `db.connect`).
- Store tests **parametrized over both stores** (proves the prod swap is safe).

**E2 — chat engine (done):**
- `producer.py`: `Producer` Protocol + `ChatProducer` (wraps provider, emits Tokens).
- `engine.py`: `send()` — persist user node → run producer relaying/accumulating
  Tokens → persist assistant node → Done. Store- and producer-agnostic.
- `router.py`: SSE endpoints on `DbStore(SessionLocal)` (real persistence):
  `POST /conversations`, `POST /conversations/{branch_id}/messages`,
  `POST /conversations/{conv_id}/fork`, `GET /conversations/branches/{id}/history`.
  Mounted in `main.py`.

**E3 — deep reasoning (done + live-proven):**
- Vendored Ouroboros at `backend/engine/ouroboros/` (tests/static stripped); loader
  `backend/engine/ouroboros_bootstrap.py` (puts `backend/engine` on sys.path so
  `import ouroboros` resolves; imports ONLY models/presets/graph/usage — never
  server/cli, so no `load_dotenv` walk-up).
- `deep_reasoning.py`: `DeepReasoningProducer` (maps Ouroboros `astream`
  updates→`Step`, usage→`Budget`, surface-node messages→`Token` final answer,
  steer→`Waiting`, end→`Complete`; fallback persists `surfaced_insight`/`synthesis`;
  cooperative `should_stop`→`Complete(status=killed)`) + `build_ouroboros_graph()`
  factory (builds ChatGroq explicitly from a passed key → never calls Ouroboros
  `get_settings`/`get_llm`; adaptive controller ON). Escalate endpoint
  `POST /conversations/{branch_id}/deep` (503 without GROQ key).
- Deps in `backend/requirements-engine.txt` (langgraph 1.2.6 / langchain 1.3.11 /
  langchain-groq, installed in `backend/.venv`; bumped pydantic-settings→2.14.2,
  websockets→15 — Helix unaffected).
- **Live Groq smoke PASSED** through `engine.send`: 22 steps, status=done,
  stop_reason=**budget** (←note: NOT converged), 4754 tokens ($0 free tier),
  coherent answer persisted. Groq key lives in `Ouroboros/.env`; Helix reads
  `settings.groq_api_key` (set `GROQ_API_KEY` in `backend/.env` for the endpoint).

**E4/E5 (done):** `DbStore` swap (one line; engine untouched), fork+history
endpoints, cooperative kill, and an `engine.send`-through-`DbStore` integration test.

### Started in session #3 but NOT wired (safe; suite still 22/22)
- `backend/api/conversation/context.py` — **created, not imported anywhere yet.**
  `build_messages(history)` (role-structured `system`+`user`/`assistant`, author-
  tagged, windowed), `render_transcript`, `render_seed` (context-aware deep-reason
  seed). This is the foundation for the shared-context-quality work below.

---

## 2. Ouroboros integration surface (reference)

`create_ouroboros_graph(llm, config, checkpointer)` → compiled graph with
`astream(inputs, config, stream_mode=["updates","messages"])` and
`aget_state(config)` (`.next` reveals a pending `steer` interrupt;
`interrupt_before=["steer"]`). `OuroborosConfig` knobs incl. the adaptive
controller (`adaptive`, `compute_budget`, `min_cycles`, `stability_threshold`,
`confidence_threshold`). Modes: explore/analyze/create/solve/philosophize.
**Key routing fact:** with `adaptive=True`, `route_after_breathe` returns
`__end__` directly — it **never routes to steer**, so adaptive runs converge in
one shot and never pause. Steer only fires in the legacy non-adaptive loop.
Usage via `new_usage_handler()` + `summarize_usage`. Evals harness lives in
`Ouroboros/evals/` (claims recursion beats single-shot).

Integration gotchas (both already avoided by the factory): (a) Ouroboros's
`load_dotenv()` walks UP and grabs Helix's root `.env` (`LLM_PROVIDER=stub`,
invalid for its `groq|openai|ollama` enum) → we never import server/cli and build
the LLM explicitly; (b) provider enums differ → keep separate.

---

## 3. THE PLAN for next session — *prove the engine works as a product (no UI)*

**Goal (user's words, session #3):** show this shared-LLM-workspace engine — the
**shared/branchable context**, **fork/branch**, **shared prompts**, and **deep
reasoning** — *actually working, robustly, usably, uniquely/novel, as a product*,
without any UI. Two deliverables: **(A) a robustness test suite** and **(B) a
narrated end-to-end demo script** (real Groq) that doubles as the no-UI live demo.

**Explicitly OUT of scope (do NOT drift into these):** WebSocket presence/
live-watch, auth/RBAC gating on conversation routes, deployment/Postgres/Redis,
frontend. Those are Mansoor's/Rajnish's lanes; the engine proof stands alone.

### Work items, in dependency order

**P1 — Shared-context quality (wire `context.py`).** *The headline "handles shared
context really well" claim.*
- Add `stream_messages(messages: list[dict])` to the provider seam: base Protocol
  + a `render_messages_to_prompt` fallback helper; Groq passes `messages` natively
  (it's OpenAI-compatible — real multi-turn context); Stub echoes last user msg;
  Ollama uses the fallback. **Keep `stream(prompt)`** intact (the week-0
  `/chat/stream` still uses it).
- `ChatProducer.run` → `build_messages(history)` → `provider.stream_messages(...)`.
- Update `test_engine.py` `CapturingProvider` to capture the messages list.
- **Proof tests:** a forked branch's `build_messages` contains exactly the ancestor
  spine and NO sibling-branch nodes (context inheritance + isolation), at depth ≥3.

**P2 — Deep reasoning context-aware.** Producer seeds via `context.render_seed(
history)` (injectable `seed_builder`, default = render_seed) instead of
`history[-1].content`, so it reasons over the thread, not one line.

**P3 — Shared prompts (F4 — the one missing core engine feature).**
- `PromptRow` (id, workspace_id, author_id, title, body, tags, created_at) + a
  `PromptStore` (save / list+search by text|tag / get), workspace-scoped.
- Endpoints: `POST/GET /workspaces/{id}/prompts`, `GET /prompts/{id}`, and an
  **insert path** (use a saved prompt's body as a conversation turn).
- **Proof:** save a "winning" prompt; reuse it across two conversations → same
  prompt drives a turn each time.

**P4 — Prove Deep Reasoning is novel & robust (close the F6/F7 gaps).**
- **Make convergence actually happen:** tune config (e.g. compute_budget≈8–10,
  reachable stability/confidence thresholds) so a settling question halts on
  `stop_reason=converged`, not `budget`. Capture the run as evidence.
- **Run the evals harness** (`Ouroboros/evals/`) to show recursion beats a
  single-shot baseline — that's the actual research/novelty number.
- **Wire steer/resume:** demonstrate pause (`Waiting`) → inject `human_input` →
  resume on the same `thread_id` (checkpointed). Adaptive never steers, so do this
  in a steer-enabled (non-adaptive or interval) config; keep adaptive as the
  default work mode.

**P5 — Robustness hardening.** Provider-failure handling on the chat path (surface
a clean error event mid-stream, not a 500); empty/edge inputs; verify the context
window bound on a long thread.

**P6 — Test suite (B-robustness).** context inheritance/isolation; deep-tree fork
(≥3 levels) correctness; prompt reuse across members; deep-reasoning convergence
(deterministic via a scripted fake graph + ONE live run marked slow); kill; steer
(fake-graph). Keep everything green and fast; gate live/Groq tests behind a marker.

**P7 — Narrated demo `backend/demo_helix.py` (real Groq).** Prints evidence each
step; the no-UI "live demo":
  1. Shared conversation, two teammates' messages → assistant answers using the
     shared context.
  2. Teammate B forks A's thread at a node → inherits context → diverges; show both
     branches evolve independently (and B's branch never sees A's later messages).
  3. Save a winning prompt to the library; reuse it in a fresh conversation.
  4. Escalate a hard question to Deep Reasoning → show the live trace (steps +
     budget meter), **convergence (`stop_reason=converged`)**, then demo kill and
     steer.
  5. Export a conversation/run to Markdown/JSON (F9, light).

### State going in
22/22 green; E1–E5 done; `context.py` scaffolded (unwired); engine deps installed;
permissions = `.claude/settings.local.json` `acceptEdits` + broad allows; all work
**uncommitted** on `main` (user said no commits).

---

## 4. Team, timeline, constraints
- **Team:** Achindra Sharma (2547105) → engine/AI + Deep Reasoning ·
  M M Mohamed Mansoor (2547132) → backend/infra/DB (presence/WS, route auth+tenancy,
  prompt-library infra, migrations) · Rajnish Kumar (2547143) → frontend/UX.
  ~6-week timeline. NOTE: this session built `DbStore` + conversation models
  (engine-adjacent) — overlaps Mansoor's DB lane; consider re-dividing so he owns
  presence + tenancy gating + prompt-library endpoints.
- **Keep it light (locked):** SQLite throughout (no Docker/Postgres/RLS until prod),
  single instance, **in-memory WebSocket rooms** (no Redis), fixed RBAC matrix. Cut:
  branch merge, editable permission policy.

## 5. Design language (locked)
**Alchemical Noir:** near-black `#0B0B0D`, antique gold `#C9A24B`, arcane violet
`#6E5AA8`, parchment text; motifs = double-helix (branching) + ouroboros (the
recursive run); serif (EB Garamond) in brand moments only. `helix-prototype.html`
+ `helix-design.html` use it; the real frontend still needs the reskin.
Artifacts: `helix-analysis-phase.md`, `helix-design-phase.md`, `helix-design.html`,
`helix-prototype.html`, plus `helix-srs.md`/`helix-proposal.md`/`helix-presentation.md`.

## 6. Immediate next action for the next session
Start **P1**: add `stream_messages` to the provider seam and wire `ChatProducer`
to `context.build_messages`, then write the context-inheritance/isolation proof
tests. Proceed P1→P7. Keep the suite green at each step. Do not build presence/
auth-gating/frontend (§3 out-of-scope). Re-read §0 before reframing anything.
