# Contributing to Helix

Thanks for looking. Helix is a multi-tenant collaborative AI workspace —
see `README.md` for what it is and `helix-product.md` for why. This doc is
the practical "how do I change something and prove it works" guide.

## Dev setup

No Docker needed for local dev — SQLite + zero infra.

```bash
cp .env.example backend/.env       # runs as-is: SQLite + stub LLM, no keys

# Terminal 1 — backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-engine.txt   # Windows
.venv/Scripts/python -m uvicorn api.main:app --reload      # http://localhost:8000

# Terminal 2 — frontend
cd frontend/app
npm install
npm run dev                    # http://localhost:5173
```

Open http://localhost:5173, register, create a workspace, and start
chatting on the `stub` provider (no key required). Set `GROQ_API_KEY` in
`backend/.env` (or paste one per-workspace under TEAM → Provider once
signed in) to talk to a real model.

## Running the tests

```bash
cd backend
./.venv/Scripts/python.exe -m pytest -q     # hermetic: stub provider, throwaway SQLite, no keys or network
```

```bash
cd frontend/app
npm run build                                # typechecks + production build
```

Both must be clean before opening a PR. The backend suite is fully
hermetic (no real API keys, no network) — it should pass identically on
your machine and in CI.

## Where things live

```
frontend/app/    React + TS + Vite (the UI)
backend/api/     FastAPI: auth, workspaces, conversations, prompts, documents, realtime
  conversation/  engine (send/ResumableRun), producers, SSE contract, store
  documents/     file grounding (RAG): ingestion, chunking, DocumentIndex
  providers/     LLM seam: groq | openai_compatible | ollama | stub
  realtime.py    workspace WebSocket rooms (presence + fan-out)
backend/engine/  vendored Ouroboros deep-reasoning engine (LangGraph)
backend/evals/   eval harness + question sets + calibration
```

`AI-LANE-CONTRACTS.md` documents the AI layer's frozen interfaces (event
kinds, endpoints, config) if you're building against it rather than
inside it.

## Good first issues

- **New LLM providers** — the `LLMProvider` protocol (`backend/api/providers/`)
  is one small interface; adding an OpenAI-compatible or new hosted provider
  is a contained addition.
- **Empty states / small-screen polish** — frontend, low-risk, high-value.
- **Redis pub/sub** behind the realtime seam (`roster()`/`broadcast()` in
  `backend/api/realtime.py`) — needed only for multi-process deployment; the
  seam is intentionally narrow.
- **Per-role tool allowlist UI** for Deep Reasoning (FR-14) — the policy
  already exists server-side; the Owner-facing UI is open.

If you're picking up something bigger, open an issue first so the design
gets discussed before code — especially anything touching the AI lane's
frozen contracts.

## Pull requests

- Keep PRs scoped to one surface (a feature, a fix, a doc pass) — easier to
  review, easier to revert if something's wrong.
- Include the test/build output in the PR description.
- If you touch an event/endpoint contract documented in
  `AI-LANE-CONTRACTS.md`, update that doc in the same PR.
- Don't commit secrets. `.env` is gitignored; use `.env.example` as the
  template for anything new.

## Code style

- Python: type-hinted, async-first (SQLAlchemy async, FastAPI). No hard
  formatter enforced yet — match the surrounding file.
- TypeScript/React: functional components, CSS Modules per route
  (`*.module.css`), Zustand for client state (`src/store/`).
- Comments explain *why*, not *what* — see the existing code for the tone
  (a comment earns its place by naming a non-obvious constraint or the
  reason behind a decision, not by restating the line below it).
