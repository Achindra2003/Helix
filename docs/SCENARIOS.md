# Helix in three rooms

A run-through of every shipped module against the three teams the product
claims to serve, asking one question of each: *does this hold for them, bend,
or break?*

The three rooms are deliberately the whole surface. A general team
brainstorming, a dev team, and a research group between them exercise every
primitive Helix has — divergent thinking, decisions that must be defended, and
evidence that must be cited. If a module holds in all three it is finished. If
it holds in one it is a vertical feature wearing horizontal clothes, and
PRODUCT.md commits to horizontal (2026-07-27).

Verdicts here are **holds** / **bends** / **breaks**, and they are about
*usability for that room*, not correctness. Everything named works.

---

## The short version

Two columns per module: where this run-through found each one (7 August), and
where it stands after Stages 0–4 of `PLAN-V1.md` (9 August). Arrows are changes.

| Module | General team | Dev team | Research team |
|---|---|---|---|
| Auth, workspaces, invites (FR-1/2) | holds | holds | holds |
| RBAC + role preview (FR-3) | holds | holds | bends → **holds** |
| Conversations + streaming (FR-4) | holds | holds | holds |
| Presence + live fan-out (FR-5) | holds | holds | holds |
| Fork & branch lineage (FR-6) | **bends** | holds | holds |
| Notes + mentions | holds | holds | holds |
| Prompt library (FR-7) | holds | holds | holds |
| Provider / BYO key (FR-8/16) | holds | holds | holds |
| Deep Reasoning + modes (FR-9/10/11) | **bends** | bends → **holds** | holds |
| Budget + guardrails (FR-12) | holds | holds | holds |
| History, replay, export (FR-13) | holds | **bends** → **holds** | **breaks** → **holds** |
| Agent tools (FR-14) | holds | **breaks** → **holds** | bends |
| Documents + grounding (FR-15) | holds | **breaks** → bends | **bends** |
| Search / recall / resurfacing | holds | bends | **breaks** |
| The Map + decisions ledger | holds | bends → **holds** | holds |

**Then:** five breaks, four of them outside the research room — the honest shape
of a product whose only evidenced audience so far was research.

**Now:** no breaks. The last one was the research room's retrieval ceiling, and
it turned out to be an implementation, not a limit — see below.

Two entries deliberately did **not** move. Fork-and-branch still bends for
brainstorming: voting gave the room a way to *converge*, but a fork is still a
dialog and a naming decision, so cheap disposable divergence is as expensive as
it was. And Deep Reasoning still bends there for the same reason it did on 7
August — you can run one question in one mode at a time, and the brainstorm move
is running two modes side by side.

### Verified end to end, not by reading

`frontend/app/e2e/rooms.mjs` walks each room's whole journey against a running
stack — a real database, a real event stream, a real agent loop, and a fake MCP
server standing in for GitHub. It asserts on the artifacts a room *leaves with*
(the export, the report, the ledger) rather than on the calls that produced
them, because every gap this document originally found lived in the space
between two features that were each individually fine. All three journeys pass.

---

## Room 1 — a general team, discussing and brainstorming

**What they do:** open a question with no right answer, generate a lot of
options quickly, argue, and leave with a decision and a reason.

### What holds

The core loop is genuinely built for this room. A thread is a shared object,
not a private tab; two people can watch the same reply stream in; a note says
something to the room that the model never reads; `@name` now asks one person
specifically, and the notice survives them closing the laptop. The prompt
library is exactly the artifact a facilitator wants ("Socratic critique",
"Adversarial red-team" ship as starters). Conclusions and branch verdicts give
the meeting its minutes, and the workspace export turns those into a document
you can hand to someone who was not there.

### What bends

**Forking is priced for decisions, not for divergence.** A fork asks for a name
and an intent, appears in a lineage list, and is designed to end in a verdict.
That is right for "we are choosing between two architectures". It is heavy for
"let's throw five ideas at this and see". Brainstorming wants cheap, disposable
branches — three at once from the same message, most of them abandoned without
ceremony. Today each is a dialog and a naming decision.

**Reasoning modes are per-run, and comparison is the brainstorm move.** Explore,
Create and Philosophize are precisely this room's modes, and they are reachable
now. But you escalate one question in one mode at a time. The thing a
brainstorm actually wants — *run this in Explore and in Solve, put them side by
side* — has no affordance, even though the engine could do it and the Map could
show it.

**Nothing converges a group.** The product can generate twelve options and has
no primitive for choosing among them. There is no reaction, no vote, no "three
of us like this one". `conversation.conclusion` is a single human-written text —
excellent as a decision record, useless as a way to *reach* the decision. For a
room whose whole job is diverge-then-converge, Helix builds the first half.

**A brainstorm is an event; Helix only has threads.** Threads never end. There
is no session, board, or "this afternoon's workshop" container, so a workspace
that runs weekly brainstorms accumulates an undifferentiated list.

### Verdict

Holds for discussion. Bends for brainstorming, in three places that are all the
same missing idea: **cheap parallel exploration and a way to converge it.**

---

## Room 2 — a dev team

**What they do:** decide a design, justify it later, review each other's work,
and keep the reasoning attached to the change it produced.

### What holds

More than you would expect. A branch *is* an alternative approach; a verdict
with a reason *is* an ADR; the workspace decisions export *is* the ADR file, and
it deliberately includes the alternative that was rejected, which is half of why
a decision holds up. BYO-key with a local Ollama means unreleased code never
leaves the building — the strongest privacy posture of the three rooms, and now
stated in plain words in the provider panel. The agent's allowlist model
(un-allowed tools are never offered, sensitive calls pause for approval) is the
right shape for a team that will not let a model touch production.

### What breaks

**Helix cannot see a repository.** Documents accept `txt`, `md`, code and
`pdf` up to 8 MB, one file at a time, through a browser upload. A dev team's
context is a repo: a tree, a diff, a blame, an issue thread. There is no
ingestion path for any of it. Everything else in this room is downstream of that
gap — you can *discuss* code Helix has never read.

**The agent's world is three tools.** `search_knowledge_base`,
`search_conversations`, `web_search`. Nothing that touches a developer's actual
day. The governance layer is excellent and it governs almost nothing.

### What bends

**The decision record has no link to the change.** A verdict says "we chose
Postgres, because…" and nothing connects it to the commit, PR or issue that
implemented it. An ADR that does not reference its change decays into folklore
within two sprints; a reader six months later cannot tell whether the decision
survived contact.

**The unit is a thread; a dev team's unit is a change.** Everything is organised
around conversations. Nothing is organised around "the work this justified".

### Verdict

The reasoning half is genuinely strong. The code half does not exist. See
*What the dev room needs*, below.

---

## Room 3 — a research group

**What they do:** read papers, explore an approach across threads, compare
methods, and produce claims that must be traceable to sources.

### What holds

This is the best-served room today and the evidence supports it: paper
ingestion, chunking, relevance-gated grounding with citation chips, deep runs
whose provenance is recorded, branch comparison of competing methods, and a
local-model posture for unpublished work. The seeded demo workspace is a real
eRisk 2025 paper for a reason.

### What breaks

**Citations are not in the record.** This is the single most important finding
in this document. Per-message grounding citations live *only in the live
stream*: they were never persisted on nodes, so the Markdown and JSON exports
deliberately omit them (PRODUCT.md states this, honestly, as a non-goal). For a
research team the citation **is** the artifact. A workspace that grounds every
answer on their own papers and then exports a decision report with no sources
has dropped the one thing the room came for. Everything else here is polish
next to this.

**Retrieval has a ceiling exactly where this room starts.** Exact cosine in
process: ~130 ms at 1,000 chunks, ~1.4 s at 10,000, comfortable to roughly 5k
for grounding. A serious literature review is 50–500 papers — tens of thousands
of chunks. The limit is documented and deliberate; it is also precisely this
room's working size.

### What bends

**A document is a filename.** No authors, year, venue, DOI. So "cite this as…"
is impossible, a bibliography cannot be produced, and two versions of the same
preprint are two unrelated files.

**Observers cannot participate.** A supervisor or reviewer invited as Observer
can read and nothing else — they cannot even leave a note. For a room whose
natural third role is "the professor who comments", read-only is very read-only.
Whether commentary should be an Observer's one write is flagged in the code
(`post_note`) as an open product question. It is this room's question.

### Verdict

Holds, and is one persistence decision away from being excellent. Persist
grounding citations on the node and put them in the export.

---

## Cross-cutting findings

**All six are now closed.** The plan they became is `PLAN-V1.md`; what each one
turned out to be is recorded here, because two of them were not what this
document first said.

1. **Citations are not persisted** — ✅ *fixed, and it was worse than written
   here.* This said "one column and one export section". It was neither: the
   only place citations existed anywhere was a module-level record in
   `ChatView.tsx`, populated from live SSE. `nodes` had no column, `get_history`
   had nothing to return, and a page reload dropped the evidence for every
   grounded answer in the thread. Now a `node_citations` table (a table, not a
   column — "which answers cite this paper?" is a query), written in the same
   transaction as the reply, hydrated on the history read, inherited across
   forks, and carried into both exports.
2. **No converge primitive** — ✅ *fixed.* `branch_votes`, approval-style: a
   member may back any number of branches. The tally is shown while a verdict is
   being written and never drives it — adopting still requires someone to write
   down why.
3. **No repo awareness** — ✅ *fixed, as MCP rather than as a GitHub
   integration.* `ToolSpec` already had MCP's shape, so a discovered tool passes
   through the allowlist, the approval gate and the tool ledger unchanged.
   Plus `conversations.subject`, which is the piece that made it useful: a team
   says "this change" for forty turns and never says the number.
4. **Documents carry no metadata** — ✅ *fixed.* Author/year/title/identifier,
   none of it inferred, and one `cite_as` rule shared by the chip, the exports
   and the model's own context so they cannot drift.
5. **Observers cannot speak** — ✅ *decided and fixed.* Option (b): notes only.
   Safe by construction rather than by policy — a note never enters the model's
   context, so an Observer cannot change a reply, spend the budget, or alter a
   thread's lineage.
6. **`REQUIREMENTS-COVERAGE.md` points at doors that have moved** — ✅ *fixed*,
   along with the retired glyphs still live in the code that this document did
   not catch (`⊙`/`◍` for visibility, `⛓` for a linked thread, `☁` beside the
   provider).

The one finding this run-through did **not** raise, and which turned out to
matter most: the agent tool layer had no telemetry at all. See `PLAN-V1.md` §2.

---

## What the dev room needs

### GitHub over MCP

The important thing here is that this is **not a new subsystem**. The tool layer
already has exactly the right shape:

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON schema for the arguments object
    handler: Callable[..., Awaitable[str]]
    sensitive: bool = False   # ⇒ human approval before every call
    available: bool = True    # ⇒ can it work in this deployment
```

An MCP server's `tools/list` maps onto that one-for-one, and `tools/call`
becomes the handler. MCP is a **catalog source**, alongside `builtin.make_tools`
— which means the two policy layers that already exist apply to it unchanged:
the owner's allowlist decides which MCP tools are offered at all, and the
approval gate pauses every sensitive call. An MCP tool inherits Helix's
governance instead of routing around it. That is the whole argument for doing it
this way, and it is worth more than the GitHub integration itself.

Four things to decide before building it, each of which is a real risk:

- **Every MCP tool should default to `sensitive=True`.** By definition it leaves
  the workspace. The default must be the safe one, with the owner able to relax
  it per tool.
- **A tool description is prompt-injection surface.** Descriptions from a
  third-party server are read by the model as instructions. They should be
  displayed to the owner verbatim in the allowlist UI before they are enabled —
  the owner is approving *text the model will obey*, not just a capability.
- **Credentials need the provider key's treatment.** A GitHub token is
  per-workspace, Fernet-encrypted at rest, write-only at the HTTP surface. That
  machinery exists (`provider_settings.py`); reuse it rather than inventing a
  second secret store.
- **A large `tools/list` costs tokens on every turn.** The allowlist is the
  budget control, and it should be presented that way.

### The reviewer: a mode, not a second agent  ✅ *built*

A "code reviewer agent" invites a parallel system — its own prompts, its own
loop, its own UI. It does not need one. Helix already had five reasoning presets
that differ by depth, energy curve, steer interval and four prompts each, chosen
per run. A reviewer is a **sixth preset** plus the GitHub tools, and its output
is already modelled: a branch with an intent, ending in a verdict with a reason,
landing in the decisions ledger and the export.

That preset now ships as `Mode.REVIEW`. The claim above was testable and it
held: the whole feature is a config, four prompts and one entry in the
advertised list — the picker, the monitor, the steer protocol, the budget, the
archive and the export all took it without modification. See `PLAN-V1.md` §4
for the one thing that was not free (a mode is also the hard-coded lists in
`graph/nodes.py` that decide how it thinks, not only its prompts).

That reuses the monitor (watch it reason, steer it, stop it), the approval gate,
the ledger and the export — and it means a review is a *record*, which is the
product's whole thesis, rather than a comment that scrolls away. It also closes
the dev room's "no link to the change": if the reviewer ran against a PR, the
run's provenance carries the PR, and the verdict is attached to it.

**Sequence, if you want one:** MCP catalog source → GitHub server behind the
existing allowlist → persist the PR reference on the run → the Review preset.
Each step is shippable alone, and the first two are useful even if the reviewer
is never built.

---

## Observability of the agent layer

Do this before the reviewer, not after. It is small and everything above makes
it more necessary.

**What already exists is good.** `api/telemetry.py` is a genuinely
industry-shaped pair: OpenTelemetry GenAI spans (opt-in, env-gated, so the
zero-infra self-host story is untouched) *and* a durable `llm_calls` ledger,
kept separate for the right reason — sampling kills billing maths. Every chat
turn and every reasoning-cycle call inside a deep run is covered.

**What is not covered is the agent.** `api/tools/` contains no tracer and no
span; `record_llm_call` is wired at the chat seam and at deep runs, and `kind`
is `chat | deep` with no `agent`. So:

> The one part of Helix that reaches **outside** the workspace is the one part
> with no durable record of what it did.

Concretely, today you cannot answer: which tools ran during that agent turn, how
long each took, what arguments they were called with, whether one failed, who
approved the sensitive call, and what it returned. The transcript shows tool
chips while it happens; nothing is queryable afterwards.

This is not ops hygiene — it is Principle 2, *nothing important happens in a
black box*, applied to the half of the system that currently is one. The monitor
made **reasoning** visible to the whole room. Tool use never got the same
treatment.

**What "industry level" would mean here, in order of value:**

1. **A run is a trace.** One root span per agent run; every tool call a child
   span carrying tool name, argument size, result size, latency, status, and —
   once MCP lands — the server identity. This is the single highest-value item
   and it is a decorator around the handler.
2. **A durable `tool_calls` ledger**, mirroring `llm_calls` for the same reason
   traces and ledgers are already separate: "what did this workspace's agent
   actually do last month" is a question about a record, not a sample.
3. **Approvals as first-class events.** Who approved, who denied, when, and for
   which call — as span events *and* ledger rows. An approval gate whose
   decisions are not recorded is a control you cannot audit, which for a
   governed tool loop is most of the point.
4. **Surface it where the team already looks.** The run archive shows finished
   reasoning runs; it should show finished agent runs the same way, with the
   tool ledger attached. The data would already exist after (1)–(3).
5. **Failure as a first-class status.** A tool that errors currently surfaces as
   a chip; it should be a span status and a ledger row, because "the agent
   silently degraded for a week" is the failure mode nobody notices.

The cost is roughly one module and a migration. The reason to do it first is
that MCP multiplies the number of things the agent can do to the outside world,
and adding capability before adding the record is how you end up unable to
answer the only question that matters after an incident.

**Built, 8 August.** Spans around every tool execution, a durable `tool_calls`
ledger, approvals and denials recorded with the deciding member, `agent` added
to the LLM ledger's `kind`, and agent runs archived beside deep runs with their
tool transcript. The `rooms.mjs` dev-team journey ends by reading the ledger
back: `get_pull_request · mcp:github · ok · 1 call · 217ms`, from an MCP server
that did not exist when this section was written.

---

## What is still open

Everything above that has not moved, in one place, so this document can be read
as a description of the product rather than a history of it.

**The retrieval ceiling — closed, and it was never a scale limit.**
This was recorded as a break: exact cosine in process, "comfortable to roughly
5k chunks", with an approximate index or an external vector store as the fix.

Measured, the truth was less interesting and much easier to fix. Both arms were
being rebuilt from scratch on *every query* — the dense arm decoded every stored
vector into a Python list and scored it with a generator expression, and BM25
re-tokenised the whole corpus to answer one question. One grounded send at
10,000 chunks cost **1.28 s**, and it was paid per message.

Nothing about that was inherent. The workspace's vectors are now one float32
matrix scored with a single matrix product, BM25 keeps postings so it only
visits documents that actually contain a query term, and both are built once and
reused until the corpus changes. Same query, same machine: **2 ms at 10,000
chunks** on that benchmark; on a harder corpus with a realistic Zipfian
vocabulary, 19 ms at 10,000 and 55 ms at 50,000 — past a 500-paper literature
review, in process, with no vector server.

Keeping a cache correct is the part that can rot, so the invariant has its own
tests (`api/documents/tests/test_corpus_revision.py`): a document is searchable
the moment it lands, stops grounding the moment it is deleted, and never leaks
into another workspace. An approximate index (pgvector/FAISS) remains the next
step up and is now genuinely a scale decision rather than a workaround.

**Three bends, all one idea.** The general room's are the same missing thing
seen from three angles: **cheap parallel exploration.**

1. *A fork costs a dialog and a name.* Right for "we are choosing between two
   architectures", heavy for "throw five ideas at this". Brainstorming wants
   three disposable branches off one message, most abandoned without ceremony.
2. *One question runs in one mode at a time.* The brainstorm move is running
   Explore and Solve on the same question and reading them side by side. The
   engine could do it; there is no affordance and the Map has nowhere to show it.
3. *A brainstorm is an event; Helix only has threads.* No session, board, or
   "this afternoon's workshop" container, so a workspace running weekly
   brainstorms accumulates an undifferentiated list.

Voting closed the *converge* half of this room's problem in Stage 1. The
*diverge* half is untouched, and it is a single feature — parallel forks with a
comparison view — rather than three.

**One bend that is now a shape, not a gap.** *Documents cannot ingest a repo*,
and after MCP they no longer need to: a dev team's repository context arrives as
tools the agent calls, under the owner's allowlist and the approval gate, rather
than as files copied into a knowledge base. Worth stating explicitly because the
original finding ("Helix cannot see a repository") reads as unresolved against
the document store and is resolved against the product.
