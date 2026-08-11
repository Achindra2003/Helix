# Plan — from the three-room run-through to v1

> **Status, 9 August 2026.** Stages 0–4 are **done**; Stage 5 (deployment) is
> not started, at the user's direction. Item 1.5 was
> decided as **(b) — Observers may write notes only**. Two things turned out
> differently from the plan below and are corrected in place: the citation break
> was larger than described (they existed *only* in browser memory), and item
> 2.6 was smaller (`status` was already first-class; the real defect was a raw
> Python exception rendered as the assistant's reply). The deployment tension
> the plan raises is unchanged and now more acute: `docker compose up` has still
> never been run.

`SCENARIOS.md` walked every module through three rooms (general team, dev team,
research team) and came back with five breaks and a list of things worth
building. This is the order to do them in, why that order, and what "done"
means for each — because a plan without a verification line is a wish.

---

## The ordering argument

Three rules decide the sequence.

**Fix what is untrue before building what is new.** A break is a feature the
product claims and does not deliver. Every one of those is worth more than a
new module, because the new module inherits the same credibility problem. The
citation break is the sharpest: it is not "citations are missing from exports"
(which `PRODUCT.md` honestly records) — it is that citations **only ever exist
in browser memory**. `ChatView.tsx:45` holds them in a module-level
`groundingByNode` record populated from live SSE; `nodes` has no column for
them; `get_history` cannot return what was never stored. Reload the page and
the evidence for an answer is gone. That is worse than the doc says, and it is
the one break that undermines the research room's entire claim.

**Observability before MCP, not after.** This is the sequencing call worth
defending. Today `api/tools/` imports no tracer at all: `run_tools` in
`agent.py:308` executes a handler, catches, and returns a string. Nothing is
spanned, nothing is written to a ledger — `llm_calls.kind` is `chat | deep`,
with no `agent` at all. So the moment MCP lands, the workspace gains tools
written by *someone else*, run against *someone else's* server, and the only
record that a call happened is a 400-character preview on an ephemeral event
stream. Adding third-party tool execution to a system with no tool telemetry is
how you get an incident you cannot reconstruct. Instrument first; then the MCP
work is observable from its first call rather than retrofitted.

**Deployment is not the last thing to think about, but it is the last thing to
do.** The recorded finish-line order is: all code, then output generation, then
deployment. That still holds — but flag the tension honestly: the rubric has a
*deployable* clause, `docker compose up` has never actually been run once, and
this plan adds six features in front of it. So Stage 5 is not optional
polish; it is a graded requirement sitting behind everything below it. If time
runs short, the cut line (bottom of this document) protects it.

---

## Stage 0 — corrections that cost nothing

**0.1 Refresh `REQUIREMENTS-COVERAGE.md`.**
It points at doors that moved: Provider settings left TEAM for SETUP, LIBR is
now PROMPTS, and it still names retired glyphs (`⚒ Agent`, `⌘ spec.md`,
`⊙ Shared`). This is the graded document and it currently misdirects a marker
who tries to follow it.
*Verify:* walk every navigation instruction in the file against the running
app; each one lands where it says.

**0.2 Move `2026-08-07-baton.txt` to the repo root** with the other batons, so
it stops sitting inside `frontend/app/src/` where the bundler can see it.
*Verify:* `npm run build` still green; file present at root.

---

## Stage 1 — the five breaks

### 1.1 Persist grounding citations  *(the big one)*

Citations are produced in three places — `producer.py:85`,
`deep_reasoning.py:152`, `tools/agent.py:88` — all yielding
`Grounding(items=[{document_id, filename, chunk_index, score, excerpt}])`, and
all of them throw the payload away once the stream ends.

Work:
- New `node_citations` table (node_id FK, document_id, filename, chunk_index,
  score, excerpt, ordinal) rather than a JSON blob on `NodeRow` — the research
  room wants "which answers cited this document", which is a query, not a
  field. Alembic migration; verify apply → downgrade → re-apply with no model
  drift, as the notices migration was.
- The assistant node's persistence path writes the citations it was given at
  the same moment it writes the content.
- `get_history` returns `citations` per node.
- `ChatView` renders from the server payload; `groundingByNode` shrinks to a
  live-stream overlay for the in-flight turn only (it stops being the source of
  truth).
- Both exports (branch Markdown, workspace decisions JSON at
  `conversation/map.py:105`) carry sources.

*Verify:* send a grounded turn, hard-reload, chips still there; export the
branch and the sources appear in the file; a second browser opening the same
thread sees the same citations.

### 1.2 A converge primitive

Branching is the product's signature and there is no counter-move. The dev and
general rooms both fork four ways and then have nothing but prose to pick a
winner. `BranchRow` already carries `intent / status(open|adopted|abandoned) /
resolution / resolved_by / resolved_at` — the schema anticipated this. What is
missing is the act: a lightweight signal from members (reaction or vote) on a
branch, and a "adopt this one" that flips status and writes the resolution into
the Map.
*Verify:* three branches, two members vote, one is adopted; the Map shows the
adopted branch and the abandoned ones differently; the decision export names
the winner and who called it.

### 1.3 Document metadata

Research uploads carry author/year/DOI/venue; the index stores a filename. A
citation reading `[smith-et-al-final-v3.pdf — part 4]` is not a citation.
Add optional metadata fields on the document row, editable after upload,
surfaced in the citation chip and the export.
*Verify:* upload a paper, fill in author/year, ask a grounded question, and the
chip and the export both read like a reference rather than a filename.

### 1.4 Repo awareness — deferred by design

This is the dev room's break, and it is the same work as Stage 3. Not done
here; done properly as MCP rather than as a bespoke integration.

### 1.5 Observers cannot speak — **needs your decision, not code**

An observer can read and cannot annotate. In the research room that costs the
role its point: a supervisor or reviewer is exactly the person who should be
able to leave a margin note without touching the thread.

Three readings, and they are genuinely different products:
- **(a) Keep it strict.** Observer is a demo/audit role. Cheapest, and the
  permission matrix stays trivially explainable.
- **(b) Observers may write notes only.** Notes are already a separate surface
  from nodes, so this is a small permission change plus tests — and it makes
  the third role earn its place.
- **(c) Add a fourth role (reviewer).** Most expressive, worst value: a fourth
  row in every matrix, every test, and every explanation, three weeks from a
  release.

Recommendation: **(b)**. It is the smallest change that stops the role being
decorative, and mentions already give it a delivery mechanism.

---

## Stage 2 — agent observability

The industry-grade version of what you asked about. The LLM layer already has
the right shape (`telemetry.py`: opt-in OTel spans + a durable `llm_calls`
ledger, deliberately separate because sampling kills billing maths). The tool
layer has none of it. Mirror the design rather than invent a second one.

**2.1 Spans around tool execution.** `run_tools` and the `gate` node get spans
using GenAI semconv (`gen_ai.operation.name = execute_tool`, `gen_ai.tool.name`,
plus `helix.run_id` / `helix.workspace_id` so a tool call groups under the run
that made it). Same opt-in gating: no OTLP endpoint, no SDK, no cost.

**2.2 A durable `tool_calls` ledger.** One row per call: workspace, run, tool
name, source (`builtin` | `mcp:<server>`), arguments digest (not raw arguments —
they can contain workspace content), status (`ok | error | denied | timeout`),
latency, result size. Fire-and-forget writes, exactly as `record_llm_call`
does, for exactly the same reason: accounting must never break a reply.

**2.3 Approvals as first-class records.** The gate is the product's safety
story and it currently leaves no trace. Every approve/deny becomes a span event
*and* a ledger row with the deciding member's id. "Who let the agent call the
web?" should be answerable a month later.

**2.4 Add `agent` to the LLM ledger's `kind`.** It is `chat | deep` today, so
agent-run spend is invisible in the same table that answers the budget
question.

**2.5 Agent runs enter the run archive.** `deep_runs` archives deep runs;
`resumable_runs.kind` is already `deep | agent`, but an agent run finishes and
leaves no durable artefact. Archive it with its tool transcript.

**2.6 Failure is a status, not a string.** `Complete(stop_reason="error: …")`
is a formatted message the UI half-parses. Give the run a real terminal status
and let the reason be detail.

*Verify:* run the hermetic suite with an in-memory span exporter installed and
assert the span tree for one agent run: agent → tool_call → gate(approved) →
tool_call. Ledger rows exist for each. With no OTLP endpoint configured, zero
spans are exported and the suite's timing is unchanged.

---

## Stage 3 — MCP as a catalog source

The insight that makes this small: **`ToolSpec` already is MCP's shape** —
`name`, `description`, `parameters` (JSON schema), `handler`, `sensitive`,
`available`. MCP's `tools/list` returns name + description + inputSchema. So
MCP is not a new subsystem; it is a *second source* feeding the existing
catalog, and every policy layer downstream (owner allowlist, approval gate,
tool spans) applies to it unchanged. That is the whole argument for why this
product can absorb MCP in days rather than weeks.

**3.1 Server registry.** Owner-configured MCP servers per workspace.
Credentials go through `provider_settings.py`'s existing Fernet machinery — no
second secret store.

**3.2 Discovery → catalog.** `tools/list` at connect time, mapped to
`ToolSpec`. Two rules that are not optional:
- **MCP tools default `sensitive=True`.** They leave the workspace by
  definition; the approval gate is the correct default, and the owner can
  demote a specific tool deliberately.
- **Descriptions are prompt-injection surface.** An MCP server's tool
  description is attacker-controlled text that goes straight into the model's
  context. Show it to the owner *verbatim* on the Tools panel at allowlist
  time, and never let it be re-fetched silently after approval — a changed
  description must re-enter review.

**3.3 GitHub server.** The dev room's repo awareness, delivered as
configuration rather than code: issues, PRs, file reads, review comments.

**3.4 PR reference on a run.** Attach a PR to a conversation the way documents
attach, so a thread about a change knows which change it is about.

*Verify:* against a real GitHub MCP server, an agent run answers "what changed
in PR #N and does it match the spec we uploaded" using one MCP tool and one
built-in document tool, with the sensitive call pausing for approval and both
calls appearing in the tool ledger.

---

## Stage 4 — the Review preset  ✅ *done*

Not a parallel agent. A **sixth reasoning mode** alongside explore / analyze /
create / solve / philosophize — same structure (depth, energy curve, steer
interval, four prompts), tuned for review: read the diff, check it against
stated intent, name what is missing, rank by severity.

Doing it as a preset rather than a separate agent is worth stating explicitly:
a parallel agent would duplicate the run machinery, the steer protocol, the
budget accounting and the archive, to end up with the same graph and a
different prompt. Reviewing is a *way of thinking*, and the product already has
a slot for ways of thinking.

*Verify:* the preset appears in the picker, runs to completion on a real PR,
respects the same budget guardrails, and its steer interval behaves like the
others under the existing preset tests.

**What it actually took.** The preset itself is what this section describes —
`Mode.REVIEW`, a config and four prompts in `engine/ouroboros/presets.py`, one
entry in `REASONING_MODES`. The picker needed no change at all: it renders
whatever `GET /conversations/deep/modes` returns, so the mode appeared in the
menu the moment the server advertised it. That is the argument for "a preset,
not an agent" holding up in practice.

The part the plan did not anticipate is that a mode is not only its prompts.
Two hard-coded mode lists in `graph/nodes.py` decide behaviour, and a new mode
lands on the *default* side of both by omission:

- `make_emotional_analysis` branches on `mode in ("analyze", "solve",
  "create")` for the practical "human perspective" prompt. Everything else gets
  a prompt asking what the thought "is avoiding, or yearning toward" — so
  Review, left out, would have psychoanalysed the author of the code under
  review. `review` was added to that list.
- `route_after_synthesis` permits one web-research detour for `analyze` and
  `solve`. Review was deliberately **left out**: the evidence a review needs is
  the diff and the workspace's own documents, both of which already reach the
  run through the seed and the grounder. A web search would spend a cycle to
  learn nothing about this change.

*Verified:* the six-item picker in a real browser at 1440×900 and 1440×768
(the menu rises out of the composer, and a sixth item does not push its top
edge off-screen — 309px and 177px of headroom respectively); choosing Review
starts a run the server archives with `provenance.mode == "review"` under the
same `compute_budget` as every other mode, and the split button remembers the
choice. 11 new tests: 8 engine-level, 3 API-level.

*Not verified, and honestly so:* "runs to completion on a real PR". That needs
a GitHub MCP server with a live credential, which this instance does not have
configured — the run above went through the stub provider. The MCP path itself
is covered by `api/tools/tests/test_mcp.py` against a fake server; what remains
unproven is the two working together on a real repository.

---

## Stage 5 — deployment and release (graded, and behind everything above)

1. `docker compose up` — actually run it, for the first time, end to end.
2. GCP: free `e2-micro` + the compose file (Track B, not Cloud Run).
3. Release surface: tag, GHCR image, licence, demo GIF.

---

## Decision needed from you

Only one item is blocked on a call rather than on work: **1.5, observer
notes** — (a) strict, (b) notes only, or (c) a fourth role. Recommendation is
(b). Everything else in this plan can proceed without you.

---

## The cut line

If time runs out, this is the order things get dropped, last-in first-out:

- **Never cut:** Stage 0, Stage 1.1 (citations), Stage 5.
- **Cut last:** Stage 2 observability — it is the differentiator when someone
  asks what makes this more than a chat wrapper.
- **Cut first:** Stage 4 (Review preset), then Stage 3.4 (PR reference), then
  Stage 1.3 (document metadata).

Stage 3 without Stage 2 is the one combination to refuse. Third-party tools
running unobserved is not a feature that shipped early; it is a hole.
