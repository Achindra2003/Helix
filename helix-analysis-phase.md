# Helix — Analysis Phase

**Project:** Helix — A Multi-Tenant Collaborative AI Workspace with Branchable
Conversations and a Monitored Deep-Reasoning Mode

**Team:** Achindra Sharma (2547105) · Rajnish Kumar (2547143) · M M Mohamed Mansoor (2547132)

---

## 1. Study of the Existing System

AI assistants such as ChatGPT, Claude, Gemini, and locally run open models have
become a routine part of how engineering teams, student project groups, and research
teams do knowledge work. Despite their capability, almost every mainstream tool is
built around a single assumption: **one user, one private conversation.** Studying how
teams actually use these tools in practice reveals five distinct categories of
existing system, each solving only one slice of collaborative AI work.

### 1.1 Categories of existing systems

| # | Category | Representative tools | What it does well | The slice it owns |
|---|---|---|---|---|
| 1 | Single-user chat assistants | ChatGPT, Claude.ai, Gemini | Fast, high-quality single-user question answering | The conversation itself |
| 2 | Team AI suites | ChatGPT Team, Claude Projects / Teams | Shared files, shared history, seat and billing management | Sharing artifacts and history |
| 3 | Prompt managers | PromptLayer, ad-hoc notebooks / spreadsheets of prompts | Storing and organising prompts | The record of prompts |
| 4 | Agent frameworks | LangChain, LangGraph, AutoGPT, CrewAI | Orchestrating autonomous multi-step reasoning agents | The reasoning loop |
| 5 | Agent observability | LangSmith, Langfuse, Helicone | Tracing and monitoring agent runs after they finish | Visibility into runs |

### 1.2 How a team works with AI today (the observed workflow)

When a team faces a hard, open-ended problem — for example, *"our retrieval-augmented
generation (RAG) product returns wrong answers about 30% of the time"* — the work
fragments without anyone deciding it should:

1. **Parallel private tabs.** Each member opens their own session and prompts the same
   model with slightly different wording. None of them can see the others' threads.
2. **Copy-paste coordination.** Useful fragments are pasted into a chat channel or a
   shared document, stripped of the surrounding conversation that gave them meaning.
3. **Destructive exploration.** When someone wants to try a different angle, they
   either overwrite their current thread or start a fresh one — losing the original
   line of thought either way. There is no record of *how* the ideas diverged.
4. **Re-inventing prompts.** A carefully crafted prompt that worked last week lives in
   one person's history; the next person rewrites it from scratch.
5. **Invisible autonomy.** For a genuinely hard question, one technically minded member
   might wire up an agent framework locally. That run is invisible to the rest of the
   team and uncontrollable once it starts — they cannot watch it, steer it, or stop it,
   and they cannot see what it is costing.

### 1.3 The gap

No single existing system combines all four of the capabilities a collaborating team
actually needs at once:

- a **shared, live** conversation surface,
- **branchable** threads that preserve lineage,
- a **reusable, searchable** prompt record, and
- a **governed, watchable** autonomous reasoning mode.

Each category in the table above owns exactly one slice, and the seams between them —
moving context from a private tab into a shared space, branching without losing the
original, reusing a teammate's prompt, watching and controlling an autonomous run — are
precisely where team effort leaks. **Helix exists to close those seams in one product.**

---

## 2. Limitations of the Existing System

The study above translates into seven concrete limitations that the proposed system
must overcome.

**L1 — Isolation and siloed context.** Conversations are private by default. A
colleague cannot see, continue, or learn from another member's thread, so the team
repeatedly re-asks questions that have already been answered. Knowledge does not
accumulate; every problem starts from zero.

**L2 — No branching; lossy exploration.** Mainstream chat tools present a single
linear thread, and "editing" an earlier message destroys the alternative rather than
preserving it. Exploring two competing approaches in parallel requires either
abandoning one or manually duplicating context, and there is no visual lineage showing
how the ideas split apart.

**L3 — No shared, reusable prompt record.** Prompts that work are trapped inside one
person's history or pasted into informal documents. There is no workspace-scoped,
tagged, searchable library, so the team continually re-invents prompts it has already
perfected.

**L4 — Autonomy without governance.** Where agent frameworks do offer multi-step
autonomous reasoning, the run is effectively a black box: there is no live trace the
team can watch, no kill switch, no way to steer the run mid-flight, and no cost ceiling.
A long autonomous run can silently drift off-topic or burn through budget.

**L5 — Weak team and tenancy model.** Single-user tools have no notion of workspace
roles at all. Team suites add seats but not fine-grained, per-action permissions — there
is no way to express, for instance, that one member may escalate to an expensive
reasoning run while another may only observe it.

**L6 — Observability is post-hoc and separate.** Dedicated observability tools trace
runs *after* they complete, inside a *different* product from where the work happens.
They offer no in-the-moment control — steer, kill, budget — fused with the workspace the
team is actually using.

**L7 — Lock-in and cost.** Most team AI is billed per seat or per token against a single
hosted provider. There is no model-agnostic option allowing a team to choose between a
hosted model and a fully local one based on cost, privacy, or latency.

---

## 3. Features of the Proposed System

Helix is a multi-tenant collaborative AI workspace — informally, **"Git for your team's
AI work."** Instead of everyone prompting alone in private tabs, a team shares one
workspace where AI conversations are shared, branchable, recorded, and — when a problem
is hard enough — escalated into a monitored deep-reasoning run. Each feature below
directly answers one or more of the limitations identified in Section 2.

| Feature | Answers | Description |
|---|---|---|
| **F1 — Multi-tenant workspaces with RBAC** | L5 | Authenticated accounts, invite-link onboarding, and three roles (Owner / Collaborator / Observer). Every resource is scoped to a single isolated workspace tenant so that no data crosses workspace boundaries. |
| **F2 — Shared and private conversations** | L1 | A conversation belongs to a workspace and is either *shared* (visible to all members) or *private* (visible only to its author). AI responses stream back token-by-token. Shared conversations become durable team knowledge. |
| **F3 — Fork and branch tree** | L2 | Any conversation can be forked at any point into an independent branch that inherits the parent context but evolves separately, visualised as a persistent Git-style tree. Forking is instantaneous because it copies no history — it records a divergence point. |
| **F4 — Shared prompt library** | L3 | Prompts that work are saved with tags and full-text search — the team's accumulated record of what has been tried and what works — and can be inserted into any conversation for reuse. |
| **F5 — Real-time collaboration and presence** | L1, L6 | A live channel per workspace broadcasts new messages, streaming tokens, and presence signals, so the workspace feels shared and members can pick up exactly where others left off. |
| **F6 — Deep Reasoning mode** | L4 | A hard, contested question can be escalated into a recursive reasoning engine that reasons, reflects on its own thinking, and synthesises — looping until it converges — instead of returning a single reply. |
| **F7 — Monitor and run control** | L4, L6 | A Deep Reasoning run is governed by a live monitor: a reasoning trace and topology view, a **kill switch**, a **steer/pause** control that injects human guidance, a recursion-depth guard, and a **token-cost budget meter** with threshold alerts. |
| **F8 — Model-agnostic provider layer** | L7 | All inference flows through one provider interface with interchangeable hosted (Groq) and local (Ollama) backends, selected purely by configuration, so a team chooses based on cost, privacy, or latency. |
| **F9 — History, replay, and export** | L1, L6 | Conversations and runs are persisted; any branch can be replayed step by step, and any conversation or run can be exported as JSON or Markdown — turning the reasoning into a kept artifact. |

Together these features demonstrate the project's three core technical concepts:
**Agentic AI** (the recursive Deep Reasoning engine), **Distributed Systems** (real-time
multi-client synchronisation, ordering, and fan-out), and **Security / RBAC**
(strict multi-tenancy with a per-action permission policy).

---

## 4. Requirement Specification

### 4.1 Functional Requirements

**FR-1 — Authentication and Accounts.** The system shall provide registration and login
with hashed credentials and shall issue signed tokens (JWT) granting authenticated
access to both REST and real-time endpoints.

**FR-2 — Workspaces and Multi-Tenancy.** The system shall allow users to create
workspaces, onboard members through invite links, and scope every resource to a single
isolated workspace tenant such that no data crosses workspace boundaries.

**FR-3 — Role-Based Access Control.** The system shall assign each member a role (Owner,
Collaborator, or Observer) and shall authorise every action — sending a message, forking,
saving or using a library prompt, escalating to Deep Reasoning, steering or killing a
run, and managing members — against a role-to-permission policy table.

**FR-4 — Shared and Private Conversations.** The system shall let members create
conversations that are either shared (visible to the whole workspace) or private
(visible only to the author), and shall stream AI responses token-by-token.

**FR-5 — Real-Time Synchronisation and Presence.** The system shall maintain one
real-time room per workspace, broadcasting new messages, streaming tokens, and presence
signals to all connected members, with a single ordered conversation state maintained as
an append-only message log with sequence numbers.

**FR-6 — Conversation Fork and Branch Tree.** The system shall allow any conversation to
be forked at any point into a child branch that inherits the parent context and evolves
independently, persisted as a node in a workspace-scoped branch tree and visualised as an
interactive tree.

**FR-7 — Shared Prompt Library.** The system shall allow members to save prompts to a
workspace-scoped library with tags, to search and browse the library, and to insert a
saved prompt into a conversation for reuse.

**FR-8 — LLM Provider Abstraction.** The system shall route all inference through a
single provider interface with interchangeable hosted (Groq) and local (Ollama) backends,
selectable by configuration without changes to application logic.

**FR-9 — Deep Reasoning Mode.** The system shall allow a member to escalate a
conversation into a Deep Reasoning run, processed by a recursive reasoning engine that
reasons, reflects, and synthesises — looping until convergence or a compute budget is
reached — and emitting a structured step event (node, thought, energy, depth, readings,
synthesis, token usage) for each transition.

**FR-10 — Deep Reasoning Monitor.** The system shall provide a live dashboard that
consumes a run's step and token events and displays the trace, a reasoning-topology
view, and current energy, depth, and loop-guard values in real time.

**FR-11 — Run Control (Kill and Steer).** The system shall provide an authorised kill
switch that halts a running Deep Reasoning run at the next step boundary, and a steer
control that pauses a run awaiting input and resumes it with injected human guidance,
subject to a recursion-depth guard.

**FR-12 — Budget Meter and Guardrails.** The system shall meter token usage and request
rate per workspace, surface them against configurable thresholds with alerts, and bound
run spend through a compute-budget halting controller.

**FR-13 — History, Replay, and Export.** The system shall persist conversations and runs,
allow any branch to be replayed step by step, and export a conversation or run as JSON or
Markdown.

**FR-14 — Permission Layer.** The system shall let an Owner restrict which tools a Deep
Reasoning run may invoke (an allowlist) and require human approval before high-risk tool
execution, layered atop the RBAC policy table.

### 4.2 Non-Functional Requirements

**NFR-1 — Performance and Latency.** Real-time events (message broadcast, presence, and
token fan-out) shall reach connected clients with a target latency under 200 ms.

**NFR-2 — Multi-Tenancy and Isolation.** The system shall enforce tenant isolation
through workspace-scoped queries and database row-level security so that no data crosses
tenant boundaries.

**NFR-3 — Cost Efficiency.** The system shall bound long-run token spend through a
compute-budget halting controller and a per-workspace budget meter, and shall run on
either hosted (Groq) or local (Ollama) models at no per-use cost.

**NFR-4 — Scalability.** The single-instance backend shall serve a workspace using
in-memory rooms; for horizontal scaling, a publish/subscribe layer may optionally
decouple real-time delivery so multiple instances can serve a workspace without session
affinity.

**NFR-5 — Security.** All endpoints shall be protected by token authentication and RBAC;
no data shall cross tenant boundaries; and Deep Reasoning tool use shall be limited to a
safe allowlist.

**NFR-6 — Reliability and Interruptibility.** Any Deep Reasoning run shall be haltable at
the next step by the kill switch, with a recursion-depth guard and compute-budget halt
preventing runaway loops, and with safe error reporting on failure.

**NFR-7 — Streaming and Backpressure.** A single response stream shall fan out to many
clients without a slow client stalling delivery to the others.

**NFR-8 — Privacy.** The system shall collect only the data needed to operate; no
biometric, audio, or video data shall be captured.

**NFR-9 — Portability.** The system shall be fully containerisable, and its provider
interface shall allow new LLM backends to be added without changes to application logic.
