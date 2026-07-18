# Helix — Team Prep (read me first)

Share this with the team. It explains **what we're presenting**, **which doc to read**,
**how to run it**, and **what each of us prepares**.

---

## What we're presenting (60-second brief)

**Helix is "Git for your team's AI work":** a multi-tenant workspace where a team
shares AI conversations, **forks** them into branches to explore ideas in parallel,
reuses winning prompts from a shared library, and escalates hard questions to a
**Deep Reasoning** mode that self-halts when the answer stabilizes — all with
role-based access and a live, controllable reasoning monitor.

**State of the build (v2, branch `v2-complete`):** the backend engine + a real
React frontend are working and wired together. **13 of 14 functional requirements
are fully delivered** (FR-14 is a server-side policy flag; the per-role UI is
future work) — including live presence + real-time fan-out over WebSockets,
server-side RBAC on every route, and guided deep runs you can steer mid-flight.
Backend tests: **64 passing**, plus a scripted 2-user live end-to-end (15/15).
The `main` branch holds the earlier presentation version.

---

## The document set — what to read

| Doc | What it's for | Who should read it |
|---|---|---|
| **TEAM-PREP.md** (this) | The entry point + prep plan | Everyone, first |
| **HELIX-STORY.md** | The narrative we tell during the demo | Everyone |
| **HELIX-DEMO-SCRIPT.md** | Who presents what; exact lines & clicks per segment | Everyone (each learns their segment) |
| **HELIX-USAGE.md** | Click-by-click how to run & use every feature | Whoever drives the keyboard; anyone practicing |
| **REQUIREMENTS-COVERAGE.md** | Each FR/NFR → status → where it's shown (vs the SRS) | Mansoor + whoever answers "what's done" |
| **helix-srs.md** | The full requirements spec | Reference for Q&A |

> Read order for a newcomer: **STORY → DEMO-SCRIPT → USAGE**, then skim
> **REQUIREMENTS-COVERAGE**.

---

## Run it on your own machine (to practice)

Full steps are in **HELIX-USAGE.md → Part 1**. Quick version:

1. **Prerequisites:** Python 3.11+, Node.js 18+.
2. **Backend deps** (first time):
   ```
   cd backend
   python -m venv .venv
   ./.venv/Scripts/python.exe -m pip install -r requirements-engine.txt -r requirements-dev.txt
   ```
3. **Create `backend/.env`** (this file is git-ignored, so it's NOT in the repo):
   ```
   LLM_PROVIDER=groq
   GROQ_API_KEY=<ask Achindra for the shared key, or use your own free Groq key>
   GROQ_MODEL=llama-3.1-8b-instant
   ```
   > ⚠ The Groq key is the one thing not in the repo. Get it from Achindra (share it
   > privately, not in the repo) or make a free one at console.groq.com.
4. **Start everything:** `./frontend/run-demo.ps1` → opens http://localhost:5173.

If you can't run it locally before the day, that's OK — **rehearse your narration
against Achindra's machine** in a screen-share.

---

## Your prep, by person

> Speakers are assigned by lane in HELIX-DEMO-SCRIPT.md. Swap if you prefer.

### Achindra — AI engine, Deep Reasoning, frontend
- **Owns segments:** Shared streaming chat (3), **Fork & branch (4)**, **Deep Reasoning (6)**, Replay/Export (7).
- **Prepare:** rehearse the **fork** until it's smooth (it's the headline), and the
  **Deep Reasoning** run — know it converges in ~7s and demo the **kill switch**.
- **Be ready to answer:** how fork is O(1) (pointers, no history copy); how Deep
  Reasoning self-halts (convergence + compute budget + kill).

### Mansoor — backend, auth & multi-tenancy, data model
- **Owns segments:** Sign-in/workspace/roles (2), Architecture + coverage (8), Roadmap (9).
- **Prepare:** be fluent in **REQUIREMENTS-COVERAGE.md** and the data model
  (workspaces/branches/nodes/prompts; SQLite dev → Postgres prod). Own the honest
  "what's next" (presence WS, route auth-gating, steer-over-HTTP, tool permissions).
- **Be ready to answer:** tenant isolation, RBAC policy-as-data, provider swap (Groq/Ollama).

### Rajnish — UI/UX, design system
- **Owns segments:** Hook/problem (1), Prompt library (5), Close (10).
- **Prepare:** the **story** (HELIX-STORY.md) and the design rationale — the
  illuminated-manuscript / scholarly look, the double-helix motif, "role legible at a
  glance," and that it's **deliberately free of occult symbolism** (we removed it).
- **Be ready to answer:** design choices, accessibility (contrast, reduced-motion),
  responsive layout.

---

## Rehearsal plan

1. **One full run-through** end-to-end with the real app (target ~10–12 min). Time it.
2. **Practice the two live/risky moments** repeatedly: the **fork** and the **Deep
   Reasoning** run (these touch the network).
3. **One person drives the keyboard**; the others narrate their segments hands-free.
4. **Rehearse the fallback** once: if Wi-Fi/Groq fails, switch to the recorded
   transcript or the narrated script (HELIX-DEMO-SCRIPT.md → fallback section).
5. **Pre-seed** a lived-in workspace before presenting (a conversation with a few
   messages) so you never start from a blank screen.

---

## Know the gaps (so nobody over-promises)

The four former gaps are now **closed on `v2-complete`** and demoable:
- **Live presence / real-time multi-user** ✅ — WebSocket room per workspace;
  open two browsers to show a teammate's reply streaming in live.
- **Steer mid-flight** ✅ — tick "⟂ guided" on Deep Reasoning; it pauses between
  cycles and anyone on the team can inject guidance.
- **Server-enforced roles** ✅ — every conversation/prompt route checks the JWT +
  membership + role; Observers are read-only at the API, not just the UI.
- **Tool policy** 🟡 — web research is gated server-side
  (`DEEP_REASONING_ALLOW_RESEARCH` + Tavily key required); a per-role allowlist
  UI with approvals is the remaining future work. Also still future: Postgres
  RLS, Redis-backed rooms for multi-process scale.

---

## Day-of checklist (pre-flight)

- [ ] Backend + app running; green **`api ✓ (groq)`** badge.
- [ ] A workspace pre-seeded with a real conversation.
- [ ] Fallback transcript open in a tab.
- [ ] Roles assigned; everyone knows their segment and cue.
- [ ] Keep Deep Reasoning questions short (tuned for a ~7s converge).
