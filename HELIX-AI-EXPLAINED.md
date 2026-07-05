# Helix — The AI, Explained

*A plain-English walkthrough of everything "AI" in Helix, from the shared
conversation context to the Ouroboros deep-reasoning engine. Written so a
teammate can read it once and confidently present their portion.*

> **How to use this doc.** It's organised as five layers, outermost to deepest.
> Sections 1–7 explain *what each piece is and why it exists*; Section 8 traces a
> live request through all of them; Section 9 suggests how to **split this into
> presentation portions** so no two people explain the same thing. Every claim
> points at the real file so you can read the source behind it.

---

## 0. The one-paragraph version

Helix is a **shared, branchable AI workspace**. A team talks to *one* assistant
inside a workspace; every message is stored as an immutable **node** in a tree, so
conversations can be **forked** like Git branches and still inherit their parent's
context. Any reply can be grounded in **another conversation's live context** (a
"reference") without copying it. Hard questions can be escalated to **Ouroboros** —
a recursive *reason → reflect → synthesize* loop that critiques and improves its
own answer until a **convergence controller** decides it has stopped improving,
then halts. Everything the model does streams to the UI as a single, uniform
**event contract**, and the actual LLM sits behind a **provider seam** so the
model vendor (Groq / Ollama / a test stub) can be swapped without touching any of
the logic above.

```
        ┌─────────────────────────────────────────────────────────┐
        │  PROVIDER SEAM   stub · Groq · Ollama   (swap the model)  │  §1
        ├─────────────────────────────────────────────────────────┤
        │  SHARED CONTEXT  one assistant, many authors, system frame│  §2
        ├─────────────────────────────────────────────────────────┤
        │  BRANCHABLE      fork = O(1) pointer; history walks spine  │  §3
        │  + REFERENCES    live cross-conversation grounding         │  §4
        ├─────────────────────────────────────────────────────────┤
        │  STREAMING ENGINE  send(): persist → stream → persist      │  §5
        │  "one mount, two producers"  (chat | deep reasoning)       │
        ├─────────────────────────────────────────────────────────┤
        │  OUROBOROS       recursive loop + convergence controller   │  §6–7
        └─────────────────────────────────────────────────────────┘
```

---

## 1. The provider seam — *how Helix talks to a model at all*

**Files:** `backend/api/providers/` (`base.py`, `groq.py`, `ollama.py`, `stub.py`,
`__init__.py`)

Everything above this layer is written against **one interface**: an
`LLMProvider` that can `stream_messages(messages)` and yield text chunks. There are
three implementations:

- **`groq`** — the real cloud models. Chat and deep reasoning are deliberately
  split: chat runs the fast small model (`GROQ_MODEL`, e.g. `llama-3.1-8b-instant`)
  while the recursive reasoning loop — whose whole value is reasoning quality —
  runs the strongest one (`DEEP_REASONING_MODEL`, default `llama-3.3-70b-versatile`).
- **`ollama`** — a local model, for offline / no-API-key runs.
- **`stub`** — a deterministic fake used by the test suite (no network), so every
  layer above can be tested end-to-end with zero cost.

`get_provider()` picks one from config (`LLM_PROVIDER` in `.env`). **Why it
matters:** "model-agnostic" isn't a slogan — no business logic ever imports Groq.
Swapping vendors is a one-line config change, and the whole stack is testable
without a key.

---

## 2. Shared context — *the heart of the product*

**File:** `backend/api/conversation/context.py`

This is the identity of Helix: **one assistant, shared by a team.** The magic is
almost entirely in how the prompt is assembled.

- **The system frame** (`SYSTEM_PROMPT`, context.py:41) tells the model it is *"the
  single shared AI assistant inside a team's collaborative workspace"* where
  *"different teammates may have written the user messages."* Each user turn is
  tagged with its author, e.g. `[alice] ...`, so the model can tell who said what —
  but it's instructed to reply in **one** assistant voice and never impersonate a
  teammate.
- **`build_messages(history, …)`** (context.py:82) turns a branch's node list into
  proper `system` / `user` / `assistant` messages (not a flattened string), keeping
  the system frame plus the most recent `DEFAULT_MAX_TURNS` (40) turns so long
  threads stay within the model's context window.

**Why it matters:** because context is assembled from the *shared* node history,
when teammate B opens teammate A's thread and asks a follow-up, the model answers
with A's full context. That's the "shared brain," and it's just careful prompt
construction over a shared store.

---

## 3. Branchable context (fork) — *Git for conversations*

**Files:** `backend/api/conversation/store.py` (the `get_history` walk),
`models.py` (the `nodes` / `branches` tables)

A conversation is a **tree of immutable nodes**. A **branch** is just a *pointer*
into that tree (the node it forked at + its current head). So **forking copies
nothing** — it inserts one branch row and is O(1) no matter how long the thread is.

The cost moves to the *read* path: to reconstruct a branch's history,
`get_history` walks the `parent_id` spine from the head back up, **transparently
crossing into the parent branch's nodes** — exactly Git's structural sharing.

```
 main:      n1 ─ n2 ─ n3 ─ n4(head)
                 │
                 └─ fork "chunk-v2" (fork_node_id = n2) ─ n5 ─ n6(head)

 reading chunk-v2  =  walk  n6 → n5 → n2 → n1   (root → head)
```

**Why it matters:** a fork inherits *exactly* its ancestors' context and nothing
from sibling branches. Two teammates can explore two directions from the same
point without their contexts bleeding into each other.

---

## 4. Cross-conversation references — *live grounding across threads*

**Files:** `context.py` (`ReferenceBlock`, `render_references`), `store.py`
(`add/remove/list_reference_ids`), `router.py` (the `/references` endpoints +
`_resolve_reference_blocks`)

A **reference is a live pointer, not a copy.** Linking thread A into thread B
stores one directed edge (`conversation_references` table). On **every turn** in B,
the server re-reads A's *current* history and folds it into a **second system
message** — clearly framed as background ("these are NOT part of this thread's own
turns"). Then it's discarded; nothing from A is persisted into B.

- Resolved fresh per turn → **stays in sync** (A grows, B sees it next turn).
- Folded into a system frame → **never pollutes B's lineage** and never gets
  mistaken for B's own messages.
- **Not recursive** — B reads A's messages, not A's links, so links can't loop.

**Why it matters:** this is the difference between "fork their thread" (inherit and
diverge inside one tree) and "reference their thread" (read another tree's live
context from your own). Proven live: a thread guessed *"PostgreSQL"* unlinked, then
answered *"CockroachDB"* — a fact that lived only in the linked thread — after
linking.

---

## 5. The streaming engine — *"one mount, two producers"*

**Files:** `backend/api/conversation/engine.py` (`send`), `producer.py`
(`ChatProducer`), `events.py` (the event contract), `router.py` (SSE wiring)

Every turn — chat *or* deep reasoning — runs through the **same** `send()` loop
(engine.py:30):

1. persist the user message as a node → emit `UserNode`
2. run the **producer** over the branch history, relaying its events and
   accumulating `Token` text into the reply
3. persist the assistant message as a node → emit `AssistantNode`
4. emit `Done`

`send()` is **producer-agnostic**: it depends only on a `Producer` interface
(`.run(history) → events`). Two producers satisfy it:

- **`ChatProducer`** — streams the provider's tokens straight through.
- **`DeepReasoningProducer`** — drives Ouroboros and emits the richer trace.

They both speak **one event contract** (`events.py`): `UserNode`, `Token`,
`AssistantNode`, `Done` for any run, plus `Step`, `Budget`, `Waiting`, `Complete`
for deep runs. These are serialised to the browser as **Server-Sent Events**
(`to_sse`). If a producer crashes mid-stream, `send()` catches it, emits a clean
terminal event, and *still* persists the partial reply — the client never sees a
torn connection.

**Why it matters:** the monitor, the persistence, and the privacy filtering are all
written once, against the event contract — deep reasoning was added as a *second
producer*, not a second pipeline.

---

## 6. Ouroboros — *the deep-reasoning engine*

**Files:** `backend/engine/ouroboros/` (the vendored engine: `graph/builder.py`,
`graph/nodes.py`, `graph/controller.py`, `graph/state.py`, `models.py`,
`presets.py`), bridged by `backend/api/conversation/deep_reasoning.py`

When a question is escalated ("Deep Reason"), Helix builds an isolated **LangGraph**
state machine and streams its reasoning. The graph (builder.py) is a recursive
loop:

```
 ingest → think → reflect ──┬─► emotional ─┐
                            ├─► logical  ──┼─► synthesize ──(route)──► think     (loop again)
                            └─► memory   ──┘                │
                                                            ├──► plan_research → research_worker(s) → think
                                                            └──► surface → remember → breathe ──► (steer?) ──► END
```

The shape that gives it its name: it **reasons, reflects on its own output, and
synthesizes — then feeds the result back into itself** until it converges. Key
nodes (nodes.py):

- **think** — generate the next thought from recent context + memories.
- **reflect → emotional / logical / memory** — three perspectives examine the
  thought *in parallel* (fan-out), then **synthesize** integrates them (fan-in).
- **synthesize (adaptive)** — the important one: it doesn't free-associate, it
  **critiques and rewrites the current best answer to the original question**,
  anchored so it can't drift, and asks the model to rate its own `CONFIDENCE`.
- **surface** — emit the final, converged answer (this is the *only* node whose
  tokens are streamed to the user as the assistant reply). In Helix it runs a
  **humanize** pass (`config.humanize`, on for chat / off for the benchmark):
  the converged synthesis is optimised for *convergence*, not for a reader, so
  surface rewrites it into a warm, conversational, lightly-Markdown answer and
  streams it token-by-token. Convergence is still measured on the terse synthesis,
  so the halting signal is unaffected.
- **breathe / remember / steer** — recover energy, store insights, and the
  human-in-the-loop pause point.

**Why it matters:** this is the headline "depth" feature, and it's a real graph
with parallelism, map-reduce research fan-out, checkpointing, and a human-in-the-
loop interrupt — not a `while` loop calling the model N times.

---

## 7. The convergence controller — *why it stops (the research wedge)*

**File:** `backend/engine/ouroboros/graph/controller.py`

A naïve reflection loop spends a **fixed** amount of compute (N iterations, or a
coin flip). Ouroboros replaces that with a **principled stop decision** from cheap
internal signals (controller.py):

- **answer stability** — semantic similarity between successive refined answers,
  over **real neural embeddings** (sentence-transformers MiniLM; a lexical
  bag-of-words fallback keeps it working offline). High stability ⇒ the loop has
  stopped changing its mind; more cycles buy little. The threshold
  **auto-calibrates to the active embedder** (0.90 neural / 0.78 lexical) because
  MiniLM cosines run far hotter than token-overlap scores. Long drafts are
  **chunk-embedded and mean-pooled** (MiniLM truncates at 256 tokens — untreated,
  a contradiction past the cutoff scored 1.0000 similarity), and stability blends
  the pooled score with a **least-anchored-sentence floor**, so a flipped
  conclusion or deleted section anywhere in a long answer buys another cycle.
- **self-confidence** — the synthesizer's own 0–1 estimate of how settled it is,
  parsed with a repair pass and **flagged when the model failed to report it** —
  an unreported placeholder can never satisfy the convergence gate.

`decide(...)` halts when, in precedence order: a hard **compute budget** is hit,
or the answer is **stable *and* confident** (`converged`). Stable-but-unconfident
— what a *stuck* loop looks like, not just a finished one — triggers
**perturb-on-stall**: the first stall issues a self-challenge (the next cycle
attacks the answer's weakest assumption) and only convergence after the
challenge, or a second stall (`no_marginal_gain`), is accepted. Repetition is
weak evidence; surviving an attack is real evidence. It's a pure function of
scalars, so it's fully unit-testable.

**Failure honesty:** transient provider errors (429/5xx/timeouts) retry with
backoff at every LLM call site; a hard failure in the synthesizer halts the run
with its own `provider_error` stop reason instead of masquerading as
convergence (the old path kept the previous answer, and
`stability(prev, prev) == 1.0` halted the run "no_marginal_gain" — a rate-limit
blip wearing a converged face).

**The dual payoff:** halting early is both the *product virtue* (you don't watch it
spin) and the way it stays inside free-tier rate limits — and it's the *research
claim* (adaptive test-time compute: spend more where the answer is still moving,
less where it has settled). One measured nuance from the July 5 pilot
(`backend/evals/FINDINGS.md`): cycle spend tracks answer *instability*, which is
not always the same thing as question *difficulty* — say it that precisely.

Alongside convergence, the run is bounded by **guards** surfaced in the monitor:
an **energy** meter (drains as it thinks, recovers on `breathe`), a **depth** cap,
a **loop-guard**, and a **token budget** meter. **Kill** stops the run cooperatively
between steps and persists whatever surfaced.

**Guided runs (steer over HTTP, FR-11).** With the composer's `⟂ guided` toggle,
the adaptive loop routes to the `steer` interrupt **between refinement cycles**
(`config.adaptive_steer`): the stream ends on a `waiting` event with a `run_id`
handle, the monitor opens a steer box, and
`POST /conversations/deep/runs/{run_id}/steer` resumes the run from its LangGraph
checkpoint with the injected guidance as the next thought — any Collaborator in
the workspace can steer, and convergence is re-measured on the steered answer.
`engine.ResumableRun` persists the user node up front and the assistant node only
on true completion, so a paused run never leaves an empty reply.

Two cost/quality guards worth naming: the **web-research detour is skipped
entirely** when there is no search backend (`TAVILY_API_KEY`) or the host policy
forbids it (`DEEP_REASONING_ALLOW_RESEARCH`, FR-14) — previously the workers
burned LLM calls feeding "[search unavailable]" placeholders back into the loop.

---

## 8. End-to-end: following one request through every layer

**A normal chat turn** (`POST /conversations/{branch}/messages`):

```
router.send_message
  → _resolve_reference_blocks(conv)        # §4  pull any linked threads' live context
  → ChatProducer(provider, references)     # §1+5 the chat producer over the provider
  → engine.send(store, producer, branch, prompt, author)
        ├ store.add_node(user)             # persist the question  → UserNode
        ├ store.get_history(branch)        # §3  walk parent spine across forks
        ├ ChatProducer.run(history)
        │     └ build_messages(history, references=…)   # §2  system frame + authored turns + refs
        │        └ provider.stream_messages(...)        # §1  → Token, Token, Token …
        ├ store.add_node(assistant)        # persist the reply    → AssistantNode
        └ Done
```

**A deep run** (`POST /conversations/{branch}/deep`) is the *same* `send()` loop,
but the producer is `DeepReasoningProducer` driving the Ouroboros graph (§6). It
emits `Step`/`Budget`/`Waiting` for the monitor as it loops, and streams the
`surface` node's tokens as the final answer the user keeps.

---

## 9. Suggested presentation split (three portions)

The architecture divides cleanly into three talkable areas of roughly equal depth.
Pick one each:

| Portion | Owns sections | The story you tell | Key files |
|---|---|---|---|
| **A — Shared & branchable context** | §2, §3, §4 | "Helix is one assistant shared by a team. Here's how a fork inherits context, and how one chat can ground on another's live context." | `context.py`, `store.py`, the `/references` endpoints |
| **B — The streaming engine & provider seam** | §1, §5 | "Every turn is persist → stream → persist over one event contract; the model vendor is swappable; deep reasoning is just a second producer." | `engine.py`, `producer.py`, `events.py`, `providers/` |
| **C — Ouroboros deep reasoning** | §6, §7 | "Escalate a hard question to a recursive reason→reflect→synthesize graph that halts when its answer converges — adaptive test-time compute." | `engine/ouroboros/graph/*`, `deep_reasoning.py` |

Each portion has its own "why it matters" line already written above — those are
your headline sentences. Section 8 is the shared map; whoever opens should walk it
once so the audience sees how the three portions connect.

---

## 10. File map (where to read the truth)

```
backend/api/
  providers/                 §1  the LLMProvider seam (stub | groq | ollama)
  conversation/
    context.py               §2  build_messages, SYSTEM_PROMPT, references, render_seed
    store.py                 §3  node/branch tree, get_history spine walk, reference links
    router.py                §4  /messages, /fork, /deep, /references endpoints
    engine.py                §5  send(): the producer-agnostic turn loop
    producer.py              §5  ChatProducer (Protocol both producers satisfy)
    events.py                §5  the one event contract + SSE serialisation
    deep_reasoning.py        §6  DeepReasoningProducer + build_ouroboros_graph (the bridge)
backend/engine/ouroboros/
    graph/builder.py         §6  the LangGraph topology (nodes + edges)
    graph/nodes.py           §6  think / reflect / synthesize / surface / breathe / steer
    graph/controller.py      §7  answer_stability + decide() — the halting logic
    presets.py, models.py    §6  modes, prompts, and OuroborosConfig (budgets, thresholds)
```

---

### The empirical layer (July 4)

The AI stack now has the discipline that separates demo-grade from
production-grade:

- **Context is managed, not truncated** (`context.py`): the window is
  token-budgeted as well as turn-capped; elided turns are admitted in a system
  note and the ones relevant to the current question come back via **semantic
  recall** over the engine's embedder; reference transcripts are per-turn
  truncated under a shared budget.
- **Prompt-injection defenses for the multiplayer surface**: referenced
  threads and recalled turns ride inside `<quoted-context>` boundaries with
  explicit data-not-instructions rules; titles are sanitized; the system frame
  declares author prefixes system-attached so in-message `[admin]` spoofs carry
  no authority.
- **Every deep run leaves a durable record** (`run_log.py`, `deep_runs` table):
  question, answer, stop reason, signal trajectories, steers, token cost, and a
  compact step trace — readable via `GET /conversations/{id}/deep/runs` and
  `/conversations/deep/runs/{run_id}/record`. Yesterday's weird run is a query,
  not a shrug.
- **An eval harness** (`backend/evals/`): an 18-question golden set, fixed-N
  baseline arms vs the adaptive controller (same production wiring, output
  parity), and a blind absolute LLM judge — the experiment that tests the
  research claim instead of asserting it.
- **And its first measured result** (pilot, July 5 — full analysis in
  `backend/evals/FINDINGS.md`): all six adaptive runs halted on genuine
  convergence (never the budget cap), and the controller **dominated the
  fixed-4 "just think longer" baseline on every tier at 29% fewer tokens**
  (8.17 vs 8.00 mean score, 5.4k vs 7.6k mean tokens). The honest other half:
  single-pass won the pilot outright (8.83 at 1.6k tokens) — on questions a
  70B model already answers well, extra refinement dilutes more than it
  deepens. So the defensible claim is narrower and better: *if you iterate,
  converge — don't count*; the next experiment is a question set hard enough
  that single-pass actually fails.

### Known rough edges (be honest in Q&A)

- **Reply formatting / "voice."** *Addressed.* Conversational system-prompt
  voice, the Ouroboros humanize rewrite (§6), and Markdown rendering in the UI.
- **Server-side RBAC.** *Addressed.* Every conversation/prompt route derives
  identity from the JWT and checks membership + role server-side; private
  threads are author-only; the realtime room is gated the same way.
- **Rigidity.** *Largely addressed* by guided runs (steer between cycles) and
  embedder-aware thresholds; per-run budget/mode controls in the UI are still
  future work.
- **Self-reported confidence.** *Mitigated, not eliminated.* Unreported ratings
  are flagged and can't satisfy the convergence gate, and perturb-on-stall stops
  a stuck loop from shipping on stability alone — but calibration (does 0.9 mean
  right 90% of the time?) is unmeasured; the run records now accumulate the data
  to measure it.
- **Energy/mood are telemetry theater** — interpretable meters from the
  engine's introspection origins, not measured signals. Say so if asked.
- **FR-14** is a server-side policy flag today, not a per-role allowlist UI.

*These are the things to say out loud rather than hide — they're scoped and known.*
