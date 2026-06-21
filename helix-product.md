# Helix — Product Definition

> **Helix: A Multi-Tenant Collaborative AI Workspace with Branchable Conversations and a Monitored Deep-Reasoning Mode**
>
> The single source of truth for *what Helix is* and *who it's for*. The SRS and
> build plan describe how it's built; this describes why.

---

## 1. What Helix is

**Helix is a collaborative AI workspace for teams.** Instead of everyone running
AI prompts alone in private tabs, a team shares one workspace where they can see
each other's conversations, pick up where a teammate left off, fork any thread to
explore alternatives, and build a shared library of prompts that worked. For hard,
open-ended problems, any conversation can be escalated into a **Deep Reasoning
mode** — a recursive reasoning run the whole team can watch, steer, and stop.

The honest one-liner: **Git for your team's AI work** — shared, branchable, and
with a record of what's already been tried.

It's model-agnostic: it runs on a hosted LLM (e.g. Groq) or fully local models
(Ollama), so a team can choose based on cost, privacy, or latency.

## 2. The core capabilities

**Shared & private conversations.** Every conversation belongs to a workspace and
is either shared (the team can see and continue it) or private (just you). The
shared ones become team knowledge; nobody re-asks what a colleague already solved.

**Fork & branch.** Any conversation can be forked at any point into an independent
branch that inherits the full context but evolves separately — explore two
approaches in parallel without losing either. A Git-style tree shows the lineage.

**Shared prompt library.** Prompts that worked are saved, tagged, and searchable.
This is the team's accumulated "what we've tried and what works" — the record
that's missing when everyone works in isolation.

**Real-time & presence.** Live updates over WebSockets show who's in the workspace
and stream responses as they generate, so the workspace feels alive and shared.

**Deep Reasoning mode (the headline).** When a question is hard and contested, a
member escalates it. Instead of a quick reply, Helix runs a recursive reasoning
engine — reason → reflect → synthesize, looping until it converges — and the whole
team watches the live trace. Because this run is long and autonomous, it comes
with a **monitor**: a live reasoning view, a **kill switch**, a **steer/pause**
control, and a **token/cost budget meter**. This is where the "agentic AI"
depth lives, and it's the moment the workspace becomes more than chat.

## 3. Who it's for

Small teams (3–15) doing knowledge work where AI is part of the workflow:

- **Dev teams** — debugging, design decisions, "what have we already tried?"
- **Student project groups** — shared research, no duplicated effort.
- **Research teams** — exploring open questions with competing approaches.

**The trigger:** *"We're all prompting the same things separately and losing track
of what worked."* That everyday pain is what Helix solves; Deep Reasoning is the
power tool for the occasional hard problem.

## 4. The user flow (in depth)

**Cast:** Aria (lead, *Owner*), Ben & Cara (*Collaborators*), Dev (PM, *Observer*).
Their RAG product gives wrong answers ~30% of the time.

**0 — Enter.** Aria creates workspace `rag-quality`, shares the invite link;
everyone joins. Dev is an Observer — can read and replay, can't edit or steer.

**1 — Everyday use (the spine).** They pull error samples, paste logs, ask quick
questions in shared conversations. Ben opens the **prompt library**, finds a
"failure-classification" prompt Cara saved last week, and reuses it — no
re-inventing. This is 80% of usage, and it just works: fast, shared, with a
record.

**2 — A promising thread → fork.** A conversation about retrieval gets promising.
Ben **forks** it to try a chunking angle without disturbing the original. Two
branches now evolve in parallel; the tree shows both.

**3 — A hard, contested question → Deep Reasoning.** Ben thinks it's retrieval;
Cara thinks chunking; two days of Slack haven't resolved it. Aria types the real
question and clicks **Deep Reasoning**. The engine spins up and the **monitor**
lights up for everyone — the reasoning unfolds live, looping and refining. They're
watching a process they can interrupt, not waiting on a black box.

**4 — Steer & stop.** The run drifts toward "evaluate five embedding models." Cara
hits **Steer**, injects a constraint ("can't change the embedding model this
quarter"), and it refocuses. Later it starts over-reasoning and the **budget
meter** alerts at 85%; they already have a crisp answer, so Aria hits **Kill** —
state saved, no wasted compute.

**5 — Capture it.** The run converges on a cheap diagnostic experiment. Aria
**exports** the branch as Markdown for the repo, and **saves the winning prompt to
the library**. Dev **replays** the session to catch up — nobody re-explains.

**6 — Next week.** The team's shared conversations, branch tree, and prompt
library are all still there. The next question builds on them instead of starting
from zero. Knowledge compounds.

## 5. Why each capability earns its place

| Moment | Capability | Why it matters |
|---|---|---|
| Everyday Q&A | Shared/private conversations | One shared surface; no isolated tabs |
| "Cara already solved this" | Prompt library | The record of what's been tried |
| Promising thread | Fork & branch | Explore alternatives without losing the original |
| Live workspace | Real-time + presence | Feels shared; pick up where others left off |
| Hard, contested question | Deep Reasoning mode | The power tool — watchable, steerable reasoning |
| Long autonomous run | Monitor: kill / steer / budget | Visibility and control over cost and direction |
| After the fact | Replay / export | The reasoning becomes a kept artefact |

## 6. Positioning

- **One sentence:** *Helix is a collaborative AI workspace where teams share and
  branch conversations, build a shared prompt library, and escalate hard problems
  into a monitored deep-reasoning mode.*
- **vs. ChatGPT Team / Claude Projects:** they share files and history; Helix
  shares *live, branchable conversations and a reusable prompt library*, plus a
  governed deep-reasoning mode.
- **vs. raw agent frameworks:** they orchestrate one agent for one developer;
  Helix makes AI work a *team* resource — shared, branchable, monitored.
- **What's distinctive:** related tools exist for each piece (team chat, prompt
  managers, agent observability). Helix's contribution is combining them — a
  shared, branchable workspace *with* a monitored deep-reasoning mode — which is
  uncommon in one product.

## 7. Scope discipline

The **collaborative core (M1–M5, M8, M9)** is the product and ships first on plain
streaming chat (Weeks 1–5). **Deep Reasoning + monitor (M6–M7)** is the headline
depth feature (Weeks 6–7) and is the cuttable layer — if engine integration runs
long, Helix still ships and demos as a complete collaborative workspace. See
`helix-build-plan.md` and `helix-srs.md`.
