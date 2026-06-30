# Project Proposal

## Helix: A Multi-Tenant Collaborative AI Workspace with Branchable Conversations and a Monitored Deep-Reasoning Mode

**Submitted in partial fulfilment of the requirements of Software Project Development**

**Submitted by:**


---

## 1. Abstract

Teams increasingly use AI for knowledge work, but today's AI tools are built for one
person in one private tab. The result: teammates run prompts in isolation, can't see
or continue each other's conversations, and keep no record of what's already been
tried — causing duplicated effort, wasted API budget, and lost progress.

**Helix** is a collaborative AI workspace that fixes this. A team shares one
workspace where conversations can be **shared or private**, any thread can be
**forked and branched** to explore alternatives, and a **shared prompt library**
captures what works. Live updates and presence make the workspace feel shared.
For hard, open-ended problems, any conversation can be escalated into a **Deep
Reasoning mode** — a recursive reasoning run the whole team can watch live, with a
**kill switch**, a **steer/pause** control, and a **cost-budget meter** so a long
autonomous run never becomes an opaque, runaway black box. Helix is model-agnostic,
running on either hosted (Groq) or local (Ollama) LLMs, so teams can adopt it on
their own terms.

---

## 2. Introduction

### 2.1 Motivation

AI has become a normal part of how dev teams, student groups, and research teams
work — but the tools haven't caught up to the fact that work is collaborative.
Knowledge gained in one person's session is invisible to everyone else; the same
prompts get re-written from scratch; and when a teammate is away, nobody can pick
up their thread. As teams start using AI for longer, more autonomous reasoning, a
second gap appears: those runs are opaque and can quietly burn time and budget. The
motivation for Helix is to make team AI work shared, reusable, and — when it gets
ambitious — observable and controllable.

### 2.2 Problem Statement

When teams do knowledge work with AI together, three problems follow:

1. **Siloed context** — Teammates can't see each other's conversations or reuse
   what's already been tried, causing redundant queries, wasted budget, and lost
   progress when someone needs to pick up where a colleague left off.
2. **No branching** — Linear chats can't fork, so a promising thread can't be
   cloned to explore an alternative without disrupting the original.
3. **Unmonitored autonomy** — Long, autonomous AI runs are opaque: no mid-run
   visibility, no stop control, and no cost guardrail — risking wasted compute and
   runaway cost before anyone can intervene.

### 2.3 Objectives

1. Provide **multi-tenant workspaces** with accounts, invite-link onboarding, and
   roles (Owner / Collaborator / Observer), with strict per-tenant isolation.
2. Support **shared and private conversations** within a workspace.
3. Deliver **real-time sync and presence** so members see updates and streaming
   responses live.
4. Implement **fork & branch** of any conversation as a persistent tree.
5. Build a **shared prompt library** with tags and search to capture reusable
   prompts.
6. Provide a **Deep Reasoning mode**: an escalation into a recursive reasoning run.
7. Provide a **monitor** for Deep Reasoning runs — live trace, kill switch,
   steer/pause, and a token/cost budget meter.
8. Persist conversations and runs for **replay and export** (JSON / Markdown).
9. Remain **model-agnostic and cost-aware** — runnable on hosted or local LLMs,
   with explicit controls on long-run token spend.

### 2.4 Existing Works

| System | Strength | Gap Helix fills |
|---|---|---|
| **ChatGPT / Claude (web)** | Strong single-user chat | One person, one tab — no sharing, branching, or library |
| **ChatGPT Team / Claude Projects** | Shared files & history | Asynchronous sharing only — no live branchable conversations or reusable prompt library |
| **Prompt managers (e.g. PromptHub)** | Prompt storage | Standalone — not tied to live team conversations or reasoning |
| **Agent frameworks (LangGraph, etc.)** | Agent orchestration | Single-developer; no collaboration, no monitoring/kill switch out of the box |

Each piece has prior art; Helix's contribution is the **combination** in one
workspace: shared + branchable conversations, a reusable prompt library, and a
monitored deep-reasoning mode — which is uncommon among existing team-AI tools.

### 2.5 Benefits of the Proposed Work

- **No duplicated effort** — shared conversations and a prompt library mean the
  team reuses what works instead of re-asking.
- **Continuity** — anyone can pick up where a teammate left off.
- **Parallel exploration** — branching lets the team try competing approaches
  without losing context.
- **Cost & oversight** — the monitor caps and controls long autonomous runs,
  cutting wasted compute (SDG 12).
- **Flexible deployment** — model-agnostic, running on hosted or local LLMs, so
  teams choose by cost, privacy, or latency.

---

## 3. Requirement Specification

### 3.1 Software Requirements

| Category | Requirement |
|---|---|
| Operating System | Cross-platform; Linux containers for deployment |
| Frontend | React, TypeScript, TailwindCSS, Vite; modern browser |
| Backend | Python 3.11+, FastAPI, WebSockets |
| Deep Reasoning engine | LangGraph (recursive reasoning, checkpointing) |
| LLM inference | Pluggable provider — Groq (hosted) or Ollama (local), via an OpenAI-compatible interface |
| Database | PostgreSQL |
| Containerisation | Docker + Docker Compose (local development) |
| Version control | Git / GitHub |
| Optional (scaling only) | Redis — pub/sub fan-out across multiple backend instances |

### 3.2 Hardware Requirements

| Component | Minimum (development) | Notes |
|---|---|---|
| CPU | Quad-core x86-64 | Backend, DB, containers |
| RAM | 8 GB (16 GB recommended) | ~8 GB if running local Ollama; otherwise use Groq |
| Storage | 10 GB free | Docker images, DB, optional model weights |
| Network | Broadband | Required for hosted inference (or run Ollama locally) |
| Client | Any modern desktop/laptop with a browser | No special hardware |
| Deployment | Any container host | No owned servers required |

---

## 4. Plan of Work

**Duration:** 8 weeks · **Team size:** 3 · **Sequencing:** build the collaborative
core first on plain chat (Weeks 1–5); add Deep Reasoning + monitor (Weeks 6–7).

**Responsibility split:** Achindra Sharma → Deep Reasoning engine & integration ·
MM Mohd. Mansoor  → Backend & infrastructure · Rajnish Kumar → Frontend & UX.
*(Roles may be adjusted by mutual agreement.)*

| Week(s) | Task / Module | Description | Person Responsible |
|---|---|---|---|
| 0 | Setup | Monorepo, Docker Compose (Postgres + Redis + Ollama), shared schemas | All |
| 1–2 | M1 — Auth & Workspace | Accounts, JWT, workspaces, invite links, roles, DB schema | Nilesh Gupta |
| 1–2 | M2 — Conversations | Provider interface (Groq/Ollama); shared & private conversations; streaming chat | Achindra Sharma |
| 1–2 | Auth & workspace UI | Login/register, workspace dashboard, chat view | Abhishek Suresh Kumar |
| 3–4 | M3 — Real-Time Sync & Presence | In-memory WebSocket rooms, presence, ordered message log (Redis optional, later) | Nilesh Gupta |
| 3–4 | Shared context | Append to shared thread, token budgeting, summarisation | Achindra Sharma |
| 3–4 | Collaboration UI | Multi-user shared view, presence avatars, stream fan-out | Abhishek Suresh Kumar |
| 5 | M4 — Fork & Branch Tree | Fork conversation via parent pointers; branch context | Achindra Sharma / Nilesh Gupta |
| 5 | M5 — Shared Prompt Library | Save/tag/search prompts; reuse into a conversation | Abhishek Suresh Kumar |
| 6–7 | M6 — Deep Reasoning Mode | Embed recursive engine; escalation path; checkpoint fork | Achindra Sharma |
| 6–7 | M7 — Monitor (backend) | Persist runs/steps, stream events, kill/steer endpoints, budget metering | Nilesh Gupta |
| 6–7 | M7 — Monitor (UI) | Deep Reasoning button, live trace/topology, kill switch, steer, budget meter | Abhishek Suresh Kumar |
| 8 | M8 — History, Replay & Export | Replay any branch; JSON/Markdown export | Achindra Sharma |
| 8 | M9 — Permission Layer | Role-gated actions; tool allowlist for Deep Reasoning | Nilesh Gupta |
| 8 | Hardening & demo | Tenant isolation (RLS), deployment, performance test, demo video, README | All |

**Minimum viable demo:** shared + private conversations with real-time sync (M1–M3),
fork a conversation (M4), reuse a library prompt (M5), and escalate one hard
question into a monitored Deep Reasoning run with a working kill switch (M6–M7).
