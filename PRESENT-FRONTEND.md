# Helix — The Frontend Lane

A technical account of the client: its architecture, design system, feature set,
and real-time behaviour — with the mechanism ("how"), the design rationale
("why"), and the transport model that ties it to the backend.

---

## 0. Architecture at a glance

A **single-page application (SPA)**: the browser loads once and swaps views
in-place via client-side routing. State is split across small **Zustand** stores;
server data is cached and revalidated by **TanStack Query**. The client speaks to
the FastAPI backend over **three channels**, each chosen for a different job:

| Channel | Used for | Why |
|---|---|---|
| HTTP (fetch) | actions & reads (login, create thread, fork) | request/response |
| **SSE** (server-sent events) | streaming AI replies token-by-token | one-way live text |
| **WebSocket** (one per workspace) | presence + live fan-out of teammates' activity | two-way, low-latency |

**Stack:** React 18, TypeScript, Vite (build), React Router (routing), Zustand
(state), TanStack Query (server cache), Framer Motion (animation).

---

## 1. The design system

**What it is.** A single, self-authored visual language ("lit parchment
manuscript"), not an off-the-shelf component kit.

**How it works.** All visual values live as **CSS custom properties (design
tokens)** in one file — surfaces, ink, accents, type scale, spacing, radii, and
motion easings. Components consume tokens, never hard-coded values, so the whole
app re-themes from one place.
- **Palette:** parchment surfaces, **oxblood** (primary action / "wax seal"),
  **gilt** (outline & accent), ink-brown text. Contrast pairs are WCAG-validated.
- **Typography — two enforced voices:** a reading serif (*IM Fell English*) for
  prose/answers, a display face (*Cinzel*) for headings, and a neutral UI font
  (*Inter*) **only** for operable controls (buttons, inputs). "Reading" and
  "operating" typography are never mixed.
- **Texture:** fixed grain + vignette + warm-glow overlays (`pointer-events:none`)
  layered above panes so every surface reads as lit, aged paper.
- **Dark mode ("Nocturne"):** the token set is overridden under
  `:root[data-theme="dark"]`; a toggle stamps the attribute and persists the
  choice. Every dark colour pair is independently contrast-checked.
- **Motion:** one shared easing (`--ease-quill`) used by both CSS and Framer, so
  every animation shares one "hand."

**Design rationale.** The product is about collaborative thinking; a generic SaaS
look would undersell it. A token-driven system also guarantees theme and motion
consistency for free.

---

## 2. The landing page

**What it is.** A public marketing/statement page (route `/`) shown before login.

**How it works.** Its own scroll container (the app shell is fixed-height).
Entrance is a **Framer staggered-children** choreography; the hero illustration
uses `useScroll`/`useTransform` for **parallax**; feature rows reveal on
`whileInView`; the evidence stats **count up** via an `useInView`-gated animation
frame loop. All motion is gated on `useReducedMotion`.

**Design rationale.** The first impression needed to *be* the pitch; previously
the app dropped users straight onto a login form.

---

## 3. The chat workspace (three panes)

**What it is.** The core screen: conversation list + branch lineage (left), the
thread (centre), the Deep Reasoning monitor (right).

**How it works — rendering.** A message is a typed `ChatMessage` (role, author,
body, tokens, grounding, tools, typing flag). The centre column maps messages to
bubbles:
- **Assistant replies render as an "illuminated leaf"** — a lit gradient panel
  with a gilt left spine and soft shadow; **user turns stay plain** with an
  author-coloured left margin, producing a clear *question → answer* rhythm.
- The first assistant reply gets a CSS `::first-letter` **drop-cap**.
- While streaming, the assistant avatar animates a breathing halo (`.avatarThinking`).
- Markdown is rendered (react-markdown + remark-gfm); citation chips, the agent
  tool ledger, and fork marks render from the message's typed fields.

**How it works — streaming.** On send, the client optimistically appends a user
bubble and an empty typing assistant bubble, opens an **SSE** stream, and mutates
the assistant bubble as events arrive (`token` appends text, `grounding` pins
citation chips, `assistant_node` finalises id + token count). Auto-scroll follows
new tokens.

**Also here:** a **replay** scrubber (purely client-side — steps through
already-fetched nodes), **export** (md/json via an authenticated route), and the
composer (Library / Deep Reasoning / Agent / guided-mode controls, a warming
focus glow, and a spring send button).

---

## 4. Branching and the Map

**What it is.** Forking any reply into a new branch, and a spatial view of the
whole workspace's reasoning.

**How it works — fork.** One click posts a fork of a node; the left `BranchTree`
re-renders from the returned branch list; reading a branch walks the ancestor
spine (the backend derives history — see the backend doc).

**How it works — the Map (`MapView`).** Layout is **deterministic, no graph
library**: a depth-first pass over the branch tree assigns **columns**, node
sequence assigns **rows**, and conversations flow left→right as "cartouches."
Spines, fork edges (Bézier curves from the divergence node), and gilt reference
arcs are emitted as SVG paths. Pan/zoom is a single `translate/scale` transform
on an SVG group; the wheel zooms around the cursor by re-solving the transform so
the point under the cursor stays fixed. Node payloads are lean; **hovering fetches
that branch's history lazily** (cached) for an excerpt card. Live **presence
dots** are placed on the branches teammates are currently viewing.

**Design rationale.** Deterministic layout keeps the map stable and debuggable and
avoids a heavy dependency; lazy excerpts keep the initial payload small.

---

## 5. Real-time collaboration

**What it is.** Multiple members experiencing one workspace together.

**How it works.** On entering a workspace the client opens the workspace
**WebSocket** and subscribes via `onRoomEvent`. A **presence store** tracks who is
online and which branch each is viewing (drives Map dots and row dots). When a
teammate sends on the branch you're viewing, their reply **streams into your
message list token-by-token** (a per-run accumulator keyed by author+branch),
identical to your own. An **unread store** dots conversations with new activity;
a **notifications store** + a bell in the top bar report a teammate's finished
deep run, and (if permitted) raise a browser `Notification` for your own
backgrounded runs.

**Design rationale.** "You can see each other think" is the collaborative payoff
of the shared store; the WebSocket makes it live without polling.

---

## 6. The Deep Reasoning monitor

**What it is.** The right pane that visualises a live deep run.

**How it works.** A **monitor store** holds run state (depth, energy, budget,
stability history, steps, answer). SVG renders a depth **ring** that spins while
running and closes into gilt light on convergence; **meters** for energy/budget;
the **reason→reflect→synthesize** topology highlighting the current node; a
**convergence sparkline** plotting stability toward the dashed halting threshold;
and a **steer box** (guided runs) that glows until answered. On reload the view
**reconnects** to an in-flight run (via the `?after=N` replay) and rebuilds the
whole monitor from the event log.

---

## 7. Supporting screens (12 views total)

- **DOCS** — knowledge-base upload with size/type validation and a "ready" state.
- **LIBRARY** — save/search/tag prompts; teammates' saves appear live; *Insert*
  runs through the same send path as chat (consistency for free).
- **TEAM** — members & roles (owner-editable), invite/revoke, the workspace
  **provider key** panel (BYO, encrypted), and the **agent-tool allowlist**.
- **Account** — change password, delete account.
- **Search overlay** — Ctrl/⌘-K workspace-wide search; hits deep-link to the
  exact conversation+branch.
- **Auth** + **workspace picker** — sign in / register; choose or create a tenant.

---

## 8. The motion & interaction layer

**What it is.** The Framer-Motion pass that makes the app feel physical.

**How it works.**
- **Route transitions:** the shell wraps the router `Outlet` in a `motion.div`
  keyed on the active view, so switching sections animates a page-turn — keyed on
  the *view*, not the conversation, so switching threads inside chat doesn't
  re-animate.
- **Rail active indicator:** a single highlight element with a Framer `layoutId`
  slides between navigation icons.
- **List entrances & controls:** shared `stagger`/`rise` variants deal list items
  in; hovers and presses use spring physics; the auth tabs use a `layoutId` pill.
- All of the above is gated on `useReducedMotion`.

**Design rationale.** One shared motion module (`lib/motion.ts`, mirroring
`--ease-quill`) keeps every surface animating in one voice.

---

## 9. Accessibility & responsiveness

- WCAG-validated contrast in **both** themes; visible keyboard-focus outlines.
- **All motion respects `prefers-reduced-motion`.**
- Responsive: the three-pane chat collapses on narrow screens; the landing page
  reflows to a single column; wide content scrolls within its own container.

---

## Quick facts

- **React 18 + TypeScript + Vite + Zustand + TanStack Query + Framer Motion.**
- **12 views**, one token-driven design system, full light + dark themes.
- Transport: **HTTP + SSE (streaming) + one WebSocket (live collaboration)**.
- Deterministic, dependency-free Map layout; SSE-driven live message rendering.
