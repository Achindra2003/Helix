# Helix

A multi-tenant **collaborative AI workspace**: shared & branchable conversations,
a shared prompt library, real-time presence, and a monitored **Deep Reasoning**
mode. See `helix-product.md` (what), `helix-srs.md` (requirements), and
`helix-build-plan.md` (how).

## Status

- **Week 0 ✅** — monorepo + vertical slice (React → FastAPI → DB, streaming LLM reply).
- **M1 ✅** — auth (register/login/JWT), workspaces, memberships + roles, invite
  links, RBAC. Verified end-to-end. See `helix-api-contract.md` §4–§5.

```
frontend/        React + TS + Vite
backend/api/     FastAPI app: auth, workspaces, providers, streaming
  routers/       auth.py, workspaces.py
  models.py      ORM (users, workspaces, memberships, invites)
backend/engine/  Deep Reasoning engine — placeholder (Weeks 6-7)
shared/          shared schemas (later)
docker-compose.yml   (optional — for Postgres/prod; not needed for dev)
```

## Quick start — no Docker needed

Dev runs on **SQLite** (a local file, zero infra). Postgres is only for prod.

```bash
cp .env.example .env          # runs as-is; SQLite + stub LLM, no keys/containers

# Terminal 1 — backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # (Windows)
.venv/Scripts/python -m uvicorn api.main:app --reload      # http://localhost:8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Open http://localhost:5173 — **backend health: ok**, send a prompt, watch it stream.
API docs at http://localhost:8000/docs.

### Switch to Postgres later
Set `DATABASE_URL=postgresql+asyncpg://helix:helix@localhost:5432/helix` in `.env`
and run `docker compose up postgres` — no code changes.

## Choosing an LLM provider

Set `LLM_PROVIDER` in `.env`:

| Value    | Needs                          | Notes                                |
|----------|--------------------------------|--------------------------------------|
| `stub`   | nothing                        | echoes the prompt; default           |
| `groq`   | `GROQ_API_KEY`                 | hosted, fast, free tier              |
| `ollama` | `docker compose --profile ollama up` then `docker compose exec ollama ollama pull llama3.2` | local, ~8GB RAM |

## Next (M2 — conversations)

Shared/private conversations persisted as the node tree (contract §6–§7), the
real streaming send endpoint replacing the `/chat/stream` stub, then the
WebSocket room for presence + live fan-out (M3, §11).
