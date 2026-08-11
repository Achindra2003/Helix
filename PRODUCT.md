# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Small teams — roughly 3 to 15 people — who already use AI daily and lose the
result. All four audiences below are in scope simultaneously; **no beachhead is
designated, and that is a deliberate decision** (2026-07-27), taken with the
tradeoff understood: reach over 90-second legibility.

- **Research groups and labs.** Ingest a paper, explore an approach across
  threads, fork to compare methods. The most evidence-backed audience today.
- **Engineering and product teams.** Decisions they will have to justify later;
  the branch, the sources and the reasoning trail become the decision record.
- **Student and course project teams.** Group work that must be shown and
  defended, with no budget — a free provider key fits exactly.
- **Any small team that thinks together.** No domain assumption.

**The job that unites them:** work whose *reasoning* has to survive — to be
reused, handed over, or defended — not just its final answer. Today that
reasoning happens in private AI tabs and dies there: the prompt that worked, the
approach that failed, the thread where the decision was actually made.

**Roles inside a workspace:** owner, collaborator, observer. Observers read;
collaborators write; owners govern invites, roles, provider settings and the
agent tool allowlist.

## Product Purpose

A shared, branchable AI workspace where a team's thinking accumulates instead of
evaporating. Conversations are team objects, not private tabs: teammates watch a
turn stream in live, fork a thread to try a different approach without losing the
original, ground answers on the team's own documents, and escalate a hard
question to a reasoning run the whole room can watch, steer mid-flight, and stop.

**Success is defined on three fronts, all three confirmed:**

1. **An open-source project people self-host** — the repository is the product;
   success is installs, self-hosters and contributors.
2. **A live hosted instance with real users** — strangers sign up, bring their
   own key, and invite a teammate. The activation event is the second person
   arriving in a workspace.
3. **A completed academic deliverable** — the project is submitted and defended.

Commercial/paid success is explicitly **not** a goal at this time.

## Positioning

**Horizontal, in the Notion sense** — one primitive the team recombines, not a
vertical tool for one discipline (decision recorded 2026-07-27).

The primitive is an **immutable node in a branchable tree**: every turn is
append-only with a parent, a per-branch sequence number, and an author. A fork is
a single row recording where it split — O(1) to create, nothing copied — so
branching a conversation is as cheap as continuing it.

What a neighboring product could not truthfully copy today:

- **Conversation as a shared, branchable, replayable object** rather than a
  private transcript — with live presence, token-level fan-out to watchers, and
  per-branch isolation.
- **A reasoning run that is observable and interruptible while it runs** — the
  team watches the trace, injects guidance between cycles, and can stop it
  server-side. Comparable tools trace after the fact, in a separate product.
- **The team's own record as retrieval substrate** — a question being typed
  resurfaces the teammate's thread that already explored it.
- **Bring-your-own-key economics** — each workspace burns its own provider key,
  so the operator's cost curve is storage and CPU, never tokens.

## Operating Context

- **Desktop web, extended sessions.** Work happens in a workspace over hours and
  returns to it over weeks. Captures and layouts to date assume ~1440×900.
- **Two people, one thread, at the same time** is the moment the product is for:
  presence, streaming attribution and live forks all exist to serve it.
- **Two deployment postures.** Self-host (one container, SQLite, optionally a
  local Ollama) and a hosted instance (Postgres, no fallback key, users bring
  their own). A hosted site cannot reach a user's local Ollama — Ollama is the
  self-host story, a hosted provider key is the hosted story.
- **The material a team brings in:** papers, specs, notes, code files — txt, md,
  code and pdf up to 8 MB, which become citable ground for replies.
- **Rituals the product already supports:** forking to explore an alternative,
  saving a prompt for the team, replaying a thread step by step, exporting a
  conversation to Markdown or JSON, reviewing a finished reasoning run.

## Capabilities and Constraints

**Delivered** (16 of 16 functional requirements; see `REQUIREMENTS-COVERAGE.md`):
accounts and JWT auth; workspaces with invites and per-workspace isolation;
server-enforced RBAC on every route; shared and private conversations with
token streaming; realtime presence and fan-out over one WebSocket room per
workspace; fork and branch lineage; a shared prompt library; a provider
abstraction (Groq, Ollama, any OpenAI-compatible endpoint) with per-workspace
encrypted keys and model choices; a recursive reasoning mode with a live monitor,
guided steering and a server-side kill; budget and guardrail meters; history,
replay and export; an agent tool loop with an owner-governed allowlist and
human approval for sensitive calls; and file grounding with citation chips.

**Known constraints, all deliberate at this milestone:**

- **Single API process.** Realtime rooms, the run registry and rate limiting are
  in-memory. Fine for a self-hosted team; a Redis swap sits behind a two-function
  seam.
- **Exact vector search, no vector database.** Embeddings live in an ordinary
  column and similarity is computed exactly, in-process. Measured: ~130 ms at
  1,000 chunks, ~1.4 s at 10,000. Comfortable to roughly 1–2k items for
  type-ahead surfaces and ~5k for grounding; beyond that needs a real index.
- **Row-level security, container-exercised deployment, and multi-instance
  scaling are open** (NFR-2, NFR-4, NFR-9 partial).
- **Paused agent and reasoning runs do not survive a server restart** — that
  layer uses an in-memory checkpointer.

**Explicitly undecided product facts** (do not invent answers to these):

- **Mobile and small-screen support** has not been established as a requirement.
- **The hosted instance is not deployed** and has no domain.

**Settled since, and no longer open:**

- **The license is MIT** (`LICENSE`, decided 2026-08-04). Helix may be described
  as MIT-licensed open source.
- **A thread can conclude.** `conversation.conclusion` records what the team
  believes, written by a human; `POST /synthesize` drafts one by reading the
  branches but is never persisted. Branch verdicts, the decisions ledger and the
  markdown export carry it. The copy-paste gap this section used to describe is
  closed; an *editable document* artifact remains unbuilt.
- **The record leaves the product as a document** (decided 2026-08-06). Export
  used to require a branch, so it produced one path — and the alternative that
  was weighed and rejected, which is half of why a decision holds, was in no
  file at all. There are now two decision reports, in Markdown and JSON:
  `GET /conversations/{id}/export` *without* a branch renders the whole
  conversation — every exploration including the abandoned ones, each verdict
  with its reason and who recorded it, the reasoning runs, the threads it drew
  context from — and `GET /workspaces/{id}/export` gathers the same decisions
  across a workspace, which is the ledger as a file. Notes render as notes in
  every export, marked as never having reached the model.
  **Not** in the reports, on purpose: per-message grounding citations. They
  live only in the live stream and were never persisted on nodes, so listing
  "the sources cited" would mean inventing them. Linked threads are recorded,
  and are listed.
- **Prompts and documents stay separate surfaces** (decided 2026-08-05). They
  looked like one duplicated idea — two places a team keeps text — but a prompt
  is something a person *inserts* into the composer and a document is something
  the model *retrieves from* on its own. Merging them would put two unrelated
  jobs behind one door. The rail label changed from `LIBR` to `PROMPTS` instead,
  so the door says what is behind it.

## Brand Commitments

- **The name is Helix**, and it is binding. The double-helix mark is the existing
  identity.
- **Vocabulary is open to renaming** (confirmed 2026-07-27). Today's UI names —
  threads, branches, forks, Deep Reasoning, the Map, resurfacing, the prompt
  Library — describe mechanisms rather than jobs, and any of them may be renamed
  for a general audience provided the engine, API and documentation stay
  accurate. Nothing in the interface vocabulary is load-bearing.
- **Identity constraint:** the project is presented in a Christ University
  academic context; occult, alchemical and hermetic motifs are out of bounds.
- **Voice, in the existing copy:** plain, specific, and willing to state its own
  limits. Documentation names what is partial rather than rounding up.

## Evidence on Hand

- **Working product** — `frontend/app` (React 18, Vite, Zustand, TanStack Query,
  Framer Motion) against a FastAPI backend; both compose files and a
  production Dockerfile (multi-stage, non-root, healthcheck) exist.
- **Test suite** — hermetic backend suite, no network or keys required (stub
  provider, throwaway SQLite): 321 collected as of 2026-07-27, green in CI on
  Linux; 6 fail on Windows for POSIX-only assumptions. Frontend typecheck and
  build are green. A Playwright end-to-end script drives the golden path.
- **Measured evaluation** — `backend/evals/FINDINGS.md` and dated result files,
  including an honest head-to-head where adaptive reasoning wins narrowly.
- **Real screenshots** — `docs/screenshots/` (light), captured by the e2e
  harness against a live backend, plus a dark set in the presentation deck.
- **Documentation** — `REQUIREMENTS-COVERAGE.md` (requirement → where to see it),
  `LAUNCH-PLAN.md`, `MARKET-VALIDATION.md`, architecture and per-lane explainers.
- **A demo workspace** with a real research paper ingested and citable.

**Absences future work must not fabricate:** there are **no real users yet**, no
testimonials, no case studies, no press, no adoption numbers, no load test, no
uptime history, no license, and no live hosted instance.

## Product Principles

1. **The record compounds, or the product has no reason to exist.** Every feature
   is judged by whether a team's past thinking becomes more reachable — not by
   whether the answer was good.
2. **Nothing important happens in a black box.** Sources, tool calls, cost, the
   reasoning trail and the moment a run decided to stop are all visible while
   they happen, and interruptible by a human.
3. **Leave a seam instead of building the infrastructure.** Ship a verified small
   system with the swap point named and measured, rather than an unverified large
   one. State the limit publicly instead of implying it away.
4. **The operator's cost must not scale with usage.** Bring-your-own-key is a
   structural commitment, not a billing convenience.
5. **Say what it is in the user's words.** Mechanism names are for the engine;
   the interface speaks to someone who has never read the architecture.

## Accessibility & Inclusion

No formal conformance standard has been established. What is already true and
must be preserved: motion respects `prefers-reduced-motion` (both in CSS and via
the animation library), streaming and status surfaces use live regions, and the
interface ships light and dark themes from one token set.
