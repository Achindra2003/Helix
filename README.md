# Helix

**The AI workspace that remembers what your team already figured out.**

Most teams run AI in private tabs and lose everything: the prompt that worked,
the approach that didn't, the thread where the decision actually happened.
Helix is "Git for your team's AI work" — shared, **branchable** conversations
where the record compounds: start typing a question and Helix resurfaces the
teammate's thread that already explored it; answers ground on your own
documents with citations; every fork, run, and source stays visible to the
whole room, live.

And when a question is genuinely hard, escalate it — **⚒ Agent** (the model
searches your knowledge base, past threads, or the web before answering,
under an owner-governed tool allowlist with human approval for anything that
leaves the workspace) or **⟳ Deep Reasoning** (a recursive run the whole team
can watch, steer, and stop, that halts itself when its answer converges).
Never a black box: you see the reasoning, the sources, the tool calls, the
cost, and the moment it decided to stop.

## See it

*The moment Helix exists for — you start typing, and the workspace remembers:*

![Proactive resurfacing: typing a question surfaces the teammate's thread that already explored it](docs/screenshots/03-resurfacing.png)

*An Agent reply: the tool ledger shows what it looked up, the answer cites the workspace's own spec:*

![Agent mode: tool ledger and cited grounding in one reply](docs/screenshots/04-agent-ledger.png)

*Deep Reasoning under supervision — live trace, meters, and a Stop button:*

![The Deep Reasoning monitor mid-run](docs/screenshots/06-deep-monitor.png)

More in [`docs/screenshots/`](docs/screenshots/) — all captured by the automated
click-through (`frontend/app/e2e/smoke.mjs`), which drives the real UI through
the whole golden path (register → workspace → streamed chat → knowledge-base
upload → cited grounding → resurfacing → agent run → deep run → map) as a
browser-level smoke test.

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
  The claim is measured, not vibes (`backend/evals/FINDINGS.md`): when you
  iterate, the controller matches fixed-4-cycle quality at **~half the
  tokens** and proves it stopped because the answer settled — transparency,
  steerability, and disciplined cost, not "more cycles = smarter."
- **Proactive resurfacing** — start typing a question and threads the
  workspace already explored appear above the composer ("✦ explored before"),
  relevance-gated on measured embedding floors so it's silent unless it's
  actually the same question. Nobody re-asks what a colleague solved.
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

Backend: **261 tests** (hermetic — stub provider + throwaway SQLite, no
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

## Install — one command

```bash
git clone https://github.com/Achindra2003/Helix.git
cd Helix
docker compose up
```

Open **http://localhost:8000**, register, create a workspace, and chat. That
is the whole install — no Python, no Node, no database server, no API key.

The container serves the API *and* the built UI on one port, stores its data
in a Docker volume (so it survives rebuilds), runs as a non-root user, and
reports health to Docker. It ships on the `stub` provider: a fake model that
echoes back, so every screen is explorable before you decide to plug in a key.

**For real model replies**, either set a key for the whole server:

```bash
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))") \
LLM_PROVIDER=groq GROQ_API_KEY=gsk_... docker compose up
```

…or let each workspace bring its own under **TEAM → Provider** in the UI.

> **Before inviting anyone**, set `JWT_SECRET` to a random value. It signs
> login tokens, and the default is a public placeholder. Changing it later
> logs everyone out and invalidates saved provider keys — their encryption is
> derived from it.

**Postgres instead of SQLite** (for a hosted deployment):

```bash
docker compose -f docker-compose.postgres.yml up
```

### About the image

~2.5 GB, because Deep Reasoning's LangGraph stack and a MiniLM embedding
model are included rather than optional — every feature works on first run,
with nothing to configure. Two deliberate choices behind that number:

- **torch is installed from PyTorch's CPU-only index.** On Linux the default
  wheel pulls the NVIDIA CUDA stack (~4.5 GB of cuBLAS, NCCL, cuSPARSELt)
  that can never execute here — there is no GPU, and torch exists only to run
  a small embedding model. Excluding it is the difference between 2.5 GB and
  roughly 7 GB.
- **The MiniLM weights are baked in at build time**, so the container runs
  fully offline and the first Deep Reasoning request doesn't stall on a
  download.

## Developing without Docker

Dev runs on **SQLite** (a local file, zero infra).

```bash
cp .env.example backend/.env       # runs as-is; SQLite + stub LLM, no keys

# Terminal 1 — backend
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-engine.txt
.venv/bin/python -m uvicorn api.main:app --reload           # http://localhost:8000
# Windows: swap .venv/bin/ for .venv/Scripts/ in both lines above

# Terminal 2 — frontend
cd frontend/app
npm install
npm run dev                    # http://localhost:5173
```

Open http://localhost:5173, register, create a workspace, and chat.
API docs at http://localhost:8000/docs.

**Install both requirements files.** `requirements-engine.txt` is not
optional for development: without it six test modules fail at *collection*
(`ModuleNotFoundError: langchain_core`) and the suite never runs. It also
brings `sentence-transformers`, so convergence and semantic memory use real
MiniLM embeddings instead of the lexical fallback (first run downloads the
model).

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
