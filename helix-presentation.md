# Helix — Presentation

> Slide deck (one `---` per slide). Render with Marp, Slidev, or reveal-md.

---

# Helix

### A Multi-Tenant Collaborative AI Workspace
### with Branchable Conversations and a Monitored Deep-Reasoning Mode

**Achindra Sharma · Nilesh Gupta · Abhishek Suresh Kumar**

*Software Project Development*

---

## The Pitch

> **Helix is a collaborative AI workspace for teams** — share and branch
> conversations, build a shared prompt library, and escalate hard problems into a
> monitored deep-reasoning mode.

*Git for your team's AI work: shared, branchable, with a record of what's been tried.*

---

## The Problem

AI tools trap each conversation in an isolated, one-on-one tab. When teams do
knowledge work with AI together, three problems follow:

- **🔒 Siloed context** — can't see each other's conversations or reuse what's been tried → redundant queries, wasted budget, lost progress.
- **➡️ No branching** — linear chats can't fork; a promising thread can't be cloned to explore an alternative.
- **👁️ Unmonitored autonomy** — long autonomous runs are opaque: no visibility, no stop control, no cost guardrail.

---

## The Idea

One shared workspace with everyday collaboration **+ one power tool**:

- **Shared & private conversations** — team knowledge, not isolated tabs.
- **Fork & branch** — explore alternatives without losing the original.
- **Shared prompt library** — the record of what works.
- **Real-time & presence** — pick up where teammates left off.
- **Deep Reasoning mode** — escalate hard problems into a *monitored* recursive reasoning run.

---

## Who It's For

- **Dev teams** — debugging, design decisions, "what have we already tried?"
- **Student project groups** — shared research, no duplicated effort.
- **Research teams** — exploring open questions with competing approaches.

**Trigger:** *"We're all prompting the same things separately and losing track of what worked."*

---

## How It Works — The Everyday Spine

```
   Team members ──> one shared Workspace
        │
        ├── Shared / private conversations  (streaming chat)
        ├── Fork any thread → Branch Tree
        ├── Shared Prompt Library (tags + search)
        └── Real-time updates + presence  (WebSockets)
```

Fast, shared, with a record. This is 80% of usage.

---

## How It Works — The Power Tool

```
   Hard question ──> click "Deep Reasoning"
        │
        ▼
   Recursive engine: reason → reflect → synthesize (loops to convergence)
        │  live trace + topology
        ▼
   MONITOR:  ⏸ Steer   ⛔ Kill   📊 Budget meter
```

A long autonomous run the whole team can watch, steer, and stop.

---

## Modules (1 / 2)

| Module | What it does |
|---|---|
| **M1 — Auth & Workspace** | Accounts, invite links, roles (Owner/Collaborator/Observer), multi-tenant isolation |
| **M2 — Shared & Private Conversations** | Streaming chat; per-conversation visibility |
| **M3 — Real-Time Sync & Presence** | WebSocket rooms; ordered shared thread |
| **M4 — Fork & Branch Tree** | Clone any thread into an independent branch; Git-style tree |
| **M5 — Shared Prompt Library** | Save, tag, and search reusable prompts |

---

## Modules (2 / 2)

| Module | What it does |
|---|---|
| **M6 — Deep Reasoning Mode** | Escalate a question into a recursive reasoning run |
| **M7 — Agent Monitor & Control** | Live trace + topology; **kill switch**, steer/pause, **budget meter** |
| **M8 — History, Replay & Export** | Replay any branch; export JSON / Markdown |
| **M9 — Permission Layer** | Role-gated actions; tool allowlist for Deep Reasoning |

---

## What Makes It Work

- **Grounded in a real pain** — duplicated effort and lost context, not a hypothetical.
- **The prompt library + branch tree** are the durable record teams actually lack.
- **Deep Reasoning** is the depth feature — and the monitor makes a long autonomous run safe to watch.
- **Model-agnostic** — runs on hosted (Groq) or local (Ollama) models.

---

## Specialisation Concepts

- **Agentic AI** — the deep-reasoning mode: a monitored, interruptible recursive loop with kill switch and budget control.
- **Distributed Systems** — real-time multi-user sync via an ordered message log and WebSocket rooms (Redis pub/sub for optional scaling).
- **Role-Based Access Control** — Owner / Collaborator / Observer via a policy table, with per-workspace isolation.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React · TypeScript · TailwindCSS · Vite |
| Backend | Python · FastAPI · WebSockets |
| Deep Reasoning | LangGraph (recursive engine) |
| AI | Groq (free) · Ollama (local) — OpenAI-compatible provider layer |
| Data | PostgreSQL (Redis optional, for scaling) |
| Infra | Docker Compose · any container host |

---

## Plan of Work (8 weeks)

| Weeks | Milestone |
|---|---|
| 0 | Setup |
| 1–2 | M1 Auth + M2 Conversations (chat) + UI |
| 3–4 | M3 Sync & presence + shared context — **Core demo #1** |
| 5 | M4 Fork tree + M5 Prompt library |
| 6–7 | M6 Deep Reasoning + M7 Monitor — **Core demo #2** |
| 8 | M8 Replay/export + M9 Permissions + hardening + deploy |

*Collaborative core ships first; Deep Reasoning is the headline depth feature.*

---

## SDG Alignment

- **SDG 9 — Industry, Innovation & Infrastructure:** infrastructure for collaborative, responsible team AI use.
- **SDG 12 — Responsible Consumption & Production:** shared context, branching, and metered runs cut redundant queries and wasted compute.

---

# Thank You

### Helix — shared, branchable, monitored AI for teams.

**Questions?**
