# Helix — UI Standout Plan (branch: `ui-standout`)

**Goal:** make Helix's differentiators *visible*. The market validation showed the
combination (team branch-tree + live references + steerable transparent reasoning
+ presence) is unclaimed — but in the current UI all of it renders as sidebar
lists and number readouts. This branch turns the thesis into the interface.

Baseline: forked from `v2-complete` (13/14 FRs, 64 tests, realtime + RBAC + guided
steer all live). Design system: light parchment, oxblood primary fill, gilt as
outline-only, scholarly-manuscript motifs, **no occult symbolism**.

Four phases, ordered by standout-per-effort. Each is independently shippable and
demoable; stop after any phase and the branch is still coherent.

---

## Phase 1 — The Map (the headline feature) ⭐

A zoomable parchment canvas showing the **team's reasoning as a graph**: every
conversation a spine of nodes, forks splitting visibly at the exact message they
diverged, references drawn as gilt threads between trees, presence dots on the
branches teammates are viewing now. Click any node → jump into that thread at
that point. *This is the first-slide screenshot: git-graph for the team's AI work.*

### 1a. Backend: one aggregate endpoint

`GET /workspaces/{wid}/map` (conversation router or a small `map.py`), gated like
every other read (any member; private conversations included **only for their
author**). One round-trip instead of N:

```json
{
  "conversations": [
    { "id", "title", "visibility",
      "branches": [ { "id", "name", "parent_branch_id", "fork_node_id", "head_node_id" } ],
      "nodes":    [ { "id", "branch_id", "seq", "role", "author_id" } ],   // no content — lean
      "references": ["conversation_id", ...] }
  ]
}
```

- Store already exposes everything (`list_branches`, `get_history`,
  `list_reference_ids`); node payloads are stripped to structure (id/branch/seq/
  role/author) so a big workspace stays a small response. Content comes lazily on
  node hover via the existing history endpoint.
- Tests: membership gate, private-thread filtering, reference edges present.

### 1b. Presence extension: "who is viewing which branch"

- **Client → server:** the room client sends `{"kind": "viewing", "branch_id"}`
  when ChatView's active branch changes (and `null` on leave). One new message
  type in `realtime.py`'s read loop; store it on the socket's info dict.
- **Server → room:** include `viewing` per user in the presence broadcast (it
  already fires on every roster change; also rebroadcast on viewing change).
- Frontend: `store/presence.ts` keeps `{user_id, email, viewing}`; Map renders a
  colored dot (existing `colorFor(email)`) on that branch; ChatView can reuse it
  later (Phase 3).
- Test: two TestClient sockets — A sends `viewing`, B's next presence frame
  carries it.

### 1c. Frontend: the Map view

- Route `/w/:wid/map` (new `routes/MapView.tsx` + rail tab "MAP" with a
  stemma/branch glyph — manuscript-appropriate, not occult).
- **Layout, no new deps:** deterministic tree layout is enough at this scale.
  Per conversation: main spine laid vertically (nodes by `seq`); child branches
  offset one column right of their parent, starting at `fork_node_id`'s y;
  columns assigned by DFS (same logic BranchTree uses for indentation, promoted
  to 2-D). Conversations flow left→right across the canvas; references drawn as
  curved dotted gilt paths between conversation title cartouches (`<path>` with
  `stroke-dasharray`).
- Rendering: plain SVG in a pan/zoom wrapper (pointer-drag + wheel, a 40-line
  hook — no library). Nodes: small ink circles, user turns filled, assistant
  turns open, fork points marked with the branch glyph; active-presence dots
  pulse gently (`prefers-reduced-motion` respected).
- Interactions: hover node → floating parchment card with the message excerpt
  (lazy `getHistory`, cached per branch); click → navigate to ChatView with that
  conversation + branch selected (ChatView already accepts conv/branch state;
  add a `?conv=&branch=` param read).
- Live: subscribe to `onRoomEvent` — `branch.created` / `conversation.created` /
  presence refetch or patch the map in place.
- Empty state: frontispiece + "Fork a conversation and the map begins."

**Acceptance:** a workspace with 2 conversations, 3 branches, 1 reference renders
as a legible graph in <1s; clicking a fork node lands in the right branch;
second browser's presence dot appears on the branch it has open; private threads
of others never appear. Typecheck + build clean.

**Effort:** the phase's bulk. Backend ~½ day incl. tests; layout+view ~1–1.5 days.
**Risk:** layout legibility at odd shapes → keep spacing generous, cap zoom-out,
and don't chase perfect edge-crossing minimization (stemma diagrams tolerate it).

---

## Phase 2 — Convergence made visible (the monitor's money-shot)

Show the answer *settling* instead of telling numbers.

- **Stability sparkline:** monitor store already receives per-step `stability`;
  keep a `stabilityHistory: number[]` on the run (patch in `handleDeepEvent`).
  Render a small inline SVG line climbing toward a dashed threshold line
  (threshold arrives with the run — add it to the `step`/`budget` payload or a
  one-field addition to the `deep_run` frame; fall back to 0.90). When the line
  crosses, it locks gilt and stamps *converged*.
- **The ring closes:** `OuroborosRing`'s `strokeDasharray` is static (210 41).
  Drive the gap from stability: gap = (1 − stability/threshold) · 60 + 4, so the
  circle visibly completes as the run converges; on `converged` the head dot
  meets the tail. (Respect reduced-motion: jump, don't tween.)
- **The steer pause moment:** when `status === "waiting"`, the pane gets a
  candle-glow treatment — dimmed trace, warm box-shadow pulse on the steer box,
  status line "⟂ the engine is holding for you". Pure CSS on existing state.
- Charts follow the project's palette (oxblood/gilt/ink on parchment) and get
  proper axes-free sparkline treatment — read the dataviz guidance before
  writing the chart code.

**Acceptance:** a live guided run shows the sparkline rising across cycles, the
ring closing, and the pause-glow when waiting; a killed run freezes both
honestly. No regression in the 64 tests (payload addition covered by the fake
graphs).

**Effort:** ~½ day. **Risk:** none structural — additive to the monitor.

---

## Phase 3 — Multiplayer legibility

Make the realtime layer *felt* without opening two browsers side-by-side:

- **Streaming attribution banner:** while a remote `run_event` streams on the
  open branch, show "✒ {author} is asking Helix…" above the composer (author
  email resolved from the members list; color via `colorFor`). Remove on `done`.
- **Author-colored margin quills:** each user message gets a thin left rule in
  its author's color (MessageList already knows `author_id`; 3-line CSS + one
  style prop). Assistant stays neutral ink.
- **Presence on conversation rows:** dots in `ConversationList` for members
  currently viewing that conversation (needs Phase 1b's `viewing` data — that's
  the dependency; conversation is derivable branch→conversation from map/branch
  data already loaded).

**Acceptance:** with two users in one thread, user B sees the banner during A's
turn and A's dot on the row; single-user experience unchanged.
**Effort:** ~½ day after Phase 1b.

---

## Phase 4 — Manuscript micro-details (perceived-quality pass)

Cheap, additive, all CSS/markup:

1. **Drop cap** on the first assistant reply of a thread (`::first-letter` on a
   `.dropCap` variant — oxblood, 3-line float).
2. **Fork glyphs in the margin** at fork points (currently hover-only): a small
   branch mark with the child branch's name on hover, always visible.
3. **Colophon metadata:** the "N tokens · ☁ groq" line restyled as a small-caps
   centered colophon with a fleuron (`❧` — already the ornament set).
4. **Export as "fair copy":** the Markdown export gains a title block + rule +
   colophon footer (backend `export_conversation` string template only).
5. **Empty/loading states:** ensure every pane's empty state uses the
   frontispiece language, not bare text.

**Effort:** ~½ day total. Do last; skip under time pressure without loss of story.

---

## Sequencing & verification

| Order | Phase | Ships alone? | Demo beat |
|---|---|---|---|
| 1 | Map (1a → 1b → 1c) | yes | "This is your team's reasoning — as a place." |
| 2 | Convergence viz | yes | "Watch it decide it's done." |
| 3 | Multiplayer legibility | yes (3rd item needs 1b) | "You can see each other think." |
| 4 | Micro-details | yes | closes the craft gap |

- Every phase: `pytest -q` green (new tests where backend changes), `tsc` +
  `vite build` clean, and one scripted/live drive of the changed surface (the
  e2e script pattern extends to the map endpoint and `viewing` frames).
- No visual regression tooling exists here — after each phase, a human
  click-through on :5173 is the eyeball check (I can't screenshot).
- Commit per phase; `v2-complete` stays stable underneath; `main` remains the
  frozen presentation version.

**Total:** ~3–4 focused days. Phase 1 alone delivers most of the standout.

## Out of scope (explicitly)

Knowledge-base/file upload, multi-model compare, agents/connectors — those are
product-gap work from the market validation, not UI, and belong on their own
branch. Nothing here migrates the DB schema; the map endpoint is read-only
aggregation. The only wire-format change is the additive `viewing` presence
field.
