# Helix

A multi-tenant **collaborative AI workspace** — "Git for your team's AI work."
Shared & branchable conversations with one team-wide assistant, live presence and
real-time fan-out over WebSockets, a shared prompt library, cross-conversation
references, a workspace knowledge base with cited RAG grounding, and a monitored,
steerable **Deep Reasoning** mode that halts itself when its answer converges —
and now grounds on that same knowledge base.

See `helix-product.md` (what), `helix-srs.md` (requirements),
`REQUIREMENTS-COVERAGE.md` (what's delivered, mapped to the SRS),
`AI-LANE-CONTRACTS.md` (the AI layer's frozen interfaces), and
`HELIX-AI-EXPLAINED.md` (how the AI layer works).

## Status

All 16 functional requirements are fully delivered and tested:

- **Auth & tenancy** — register/login/JWT, workspaces, role-carrying invite
  links; RBAC enforced **server-side** on every conversation/prompt route.
- **Conversations** — shared/private threads, real token streaming (SSE), an
  immutable node tree, O(1) **fork** with context inheritance, live
  **cross-conversation references**, replay, and authenticated export (md/json).
- **Real-time** — a WebSocket room per workspace: presence rosters (including
  *which branch* each teammate is reading), and teammates' turns stream into
  your open thread token-by-token — named in a live attribution banner, with
  author-colored margins; you can even live-watch a teammate's Deep Reasoning
  trace.
- **The Map** — the workspace's reasoning as a zoomable graph: every
  conversation a spine of turns, forks splitting at the exact message they
  diverged, references drawn as gilt threads between threads, live presence
  dots on the branches teammates have open. Click any node to land there.
- **Deep Reasoning (Ouroboros)** — recursive reason → reflect → synthesize on
  the 70B model with semantic-convergence halting, budget caps, kill switch,
  and **guided mode**: the run pauses between cycles so anyone on the team can
  steer it mid-flight. The monitor shows convergence happening: a stability
  sparkline climbing to the halting threshold and the ouroboros ring closing.
- **Prompt library** — save/tag/search/insert, updating live for the room.
- **Knowledge base (file grounding / RAG)** — upload documents to a workspace;
  chat **and** Deep Reasoning replies ground on relevant chunks automatically,
  with citation chips, when relevance clears a measured floor. Closes the #1
  gap named in `MARKET-VALIDATION.md`.
- **Agent mode (tool loop)** — the composer's ⚒ Agent button lets the model
  *search before it speaks*: the knowledge base, past conversations, or the
  web. Owners govern exactly which tools exist (TEAM → Agent tools); tools
  that leave the workspace pause for a member's approval before every call
  (human-in-the-loop, checkpointed server-side); each reply shows its tool
  ledger. Un-allowed tools are never even offered to the model.
- **Per-workspace provider settings (BYO API key)** — each workspace can plug
  in its own Groq (or OpenAI-compatible) key and models, encrypted at rest,
  with retry/circuit-breaker/safe-fallback on every call. Server `.env`
  values remain the fallback for self-host.
- **Durable, resilient deep runs** — Deep Reasoning executes server-side, so
  closing the tab doesn't kill a run; reconnect on reload, an explicit Stop
  button, a per-workspace queue, and a Run history archive with provenance
  (which model/thresholds produced each run).

Backend: **257 tests** (hermetic — stub provider + throwaway SQLite, no
keys or network required; includes an adversarial injection-regression suite).
Frontend: React 18 + Vite + TS, builds clean.
Market context: see `MARKET-VALIDATION.md` (July 2026 landscape).

```
frontend/app/    React + TS + Vite (the real UI)
backend/api/     FastAPI: auth, workspaces, conversations, prompts, realtime
  conversation/  engine (send/ResumableRun), producers, SSE contract, store
  realtime.py    workspace WebSocket rooms (presence + fan-out)
  providers/     LLM seam: groq | ollama | stub
backend/engine/  vendored Ouroboros deep-reasoning engine (LangGraph)
docker-compose.yml   (optional — for Postgres/prod; not needed for dev)
```

## Quick start — no Docker needed

Dev runs on **SQLite** (a local file, zero infra). Postgres is only for prod.

```bash
cp .env.example backend/.env       # runs as-is; SQLite + stub LLM, no keys

# Terminal 1 — backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-engine.txt   # (Windows)
.venv/Scripts/python -m uvicorn api.main:app --reload      # http://localhost:8000

# Terminal 2 — frontend
cd frontend/app
npm install
npm run dev                    # http://localhost:5173
```

Open http://localhost:5173, register, create a workspace, and chat.
API docs at http://localhost:8000/docs.
`requirements-engine.txt` includes `sentence-transformers` so convergence and
semantic memory use real MiniLM embeddings (first run downloads the model).

### Switch to Postgres later
Set `DATABASE_URL=postgresql+asyncpg://helix:helix@localhost:5432/helix` in
`backend/.env` and run `docker compose up postgres` — no code changes.

## Choosing an LLM provider

Set `LLM_PROVIDER` in `backend/.env`:

| Value    | Needs                          | Notes                                |
|----------|--------------------------------|--------------------------------------|
| `stub`   | nothing                        | echoes the prompt; default           |
| `groq`   | `GROQ_API_KEY`                 | hosted, fast, free tier              |
| `ollama` | `docker compose --profile ollama up` then `docker compose exec ollama ollama pull llama3.2` | local, ~8GB RAM |

Deep Reasoning always runs on Groq and uses its own model
(`DEEP_REASONING_MODEL`, default the 70B) so chat can stay on a fast small
model while the reasoning loop gets the strongest one.

## Roadmap (post-v2)

- Per-conversation model picker (today the provider/model is set once per
  workspace) and agents/connectors — the next wave of market gaps.
- Postgres row-level security + Alembic migrations for prod hardening.
- Redis pub/sub behind the realtime seam for multi-process deployment.
- A blob store for original uploaded files (today only extracted text is
  kept; re-upload re-ingests).
