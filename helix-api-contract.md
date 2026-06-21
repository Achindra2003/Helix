# Helix — API Contract (v0.1)

> The interface frontend and backend build against in parallel. Grounded in the
> data model and modules of `helix-build-plan.md` / `helix-srs.md`.
>
> **Transports:** REST (CRUD), **WebSocket** (one room per workspace: presence +
> live broadcast), **SSE** (LLM token streams). `[impl]` = already scaffolded in
> Week 0; everything else is the agreed target, built incrementally.

---

## 1. Conventions

- **Base URL:** `http://localhost:8000` (dev). All REST under `/api` except
  `/health`. WebSocket under `/ws`.
- **Format:** JSON in/out, UTF-8. Request bodies `application/json`.
- **Auth:** `Authorization: Bearer <JWT>` on everything except `/health`,
  `/api/auth/register`, `/api/auth/login`, and invite-link preview.
- **IDs:** server-generated UUID strings (`"id": "uuid"`).
- **Timestamps:** ISO-8601 UTC (`2026-06-20T10:30:00Z`).
- **Tenancy:** every resource below `/api/workspaces/{wid}` is scoped to that
  workspace; the server rejects cross-tenant access with `403`.
- **Pagination:** list endpoints accept `?limit=` (default 50, max 200) and
  `?cursor=` (opaque); responses return `{ "items": [...], "next_cursor": null }`.
- **Errors:** uniform shape, never a bare string —
  ```json
  { "error": { "code": "forbidden", "message": "Observers cannot send prompts." } }
  ```
  Codes: `bad_request` (400), `unauthorized` (401), `forbidden` (403),
  `not_found` (404), `conflict` (409), `rate_limited` (429),
  `provider_error` (502), `internal` (500).

---

## 2. Roles (RBAC — M9)

`Owner` ⊃ `Collaborator` ⊃ `Observer`. The policy is data, not code (the
`permissions` table); this matrix is the default seed.

| Action | Owner | Collaborator | Observer |
|---|:---:|:---:|:---:|
| read conversations / replay | ✓ | ✓ | ✓ |
| send prompt / message | ✓ | ✓ | ✗ |
| fork conversation | ✓ | ✓ | ✗ |
| save/edit prompt library | ✓ | ✓ | ✗ |
| escalate → Deep Reasoning | ✓ | ✓ | ✗ |
| steer / kill a run | ✓ | ✓ | ✗ |
| invite / change roles | ✓ | ✗ | ✗ |
| edit permission policy | ✓ | ✗ | ✗ |

A forbidden action returns `403 { error.code: "forbidden" }`.

---

## 3. Health `[impl]`

`GET /health` → `200`
```json
{ "status": "ok", "db_time": "2026-06-20T10:30:00Z", "provider": "stub" }
```

---

## 4. Auth & Users (M1)

`POST /api/auth/register` → `201`
```json
// req
{ "email": "aria@team.dev", "password": "•••••" }
// res
{ "user": { "id": "uuid", "email": "aria@team.dev" }, "token": "jwt" }
```

`POST /api/auth/login` → `200` → same `{ user, token }` shape.
`409 conflict` if email taken; `401 unauthorized` on bad credentials.

`GET /api/me` → `200` `{ "id", "email", "created_at" }` (current user from JWT).

---

## 5. Workspaces & Membership (M1)

**Workspace** `{ "id", "name", "owner_id", "role", "created_at" }`
(`role` = the caller's role in it).

| Method | Path | Body / Notes | Returns |
|---|---|---|---|
| `GET`  | `/api/workspaces` | the caller's workspaces | `{ items: Workspace[] }` |
| `POST` | `/api/workspaces` | `{ "name" }` → caller becomes Owner | `201 Workspace` |
| `GET`  | `/api/workspaces/{wid}` | | `Workspace` |
| `POST` | `/api/workspaces/{wid}/invites` | Owner only → invite link | `201 { "token", "url", "expires_at" }` |
| `GET`  | `/api/invites/{token}` | preview (no auth) | `{ "workspace_name" }` |
| `POST` | `/api/invites/{token}/accept` | join as Collaborator | `200 Workspace` |
| `GET`  | `/api/workspaces/{wid}/members` | | `{ items: Member[] }` |
| `PATCH`| `/api/workspaces/{wid}/members/{uid}` | Owner: `{ "role" }` | `Member` |

**Member** `{ "user_id", "email", "role", "joined_at" }`.

---

## 6. Conversations (M2)

**Conversation**
```json
{ "id", "workspace_id", "author_id", "title",
  "visibility": "shared|private", "default_branch_id", "created_at" }
```

| Method | Path | Body / Notes | Returns |
|---|---|---|---|
| `GET`  | `/api/workspaces/{wid}/conversations` | `?visibility=shared\|private\|all` | `{ items: Conversation[] }` |
| `POST` | `/api/workspaces/{wid}/conversations` | `{ "title", "visibility" }` | `201 Conversation` (+ a root branch) |
| `GET`  | `/api/workspaces/{wid}/conversations/{cid}` | | `Conversation` |
| `PATCH`| `/api/workspaces/{wid}/conversations/{cid}` | `{ "title"?, "visibility"? }` | `Conversation` |

Private conversations are visible only to their `author_id`; shared ones to all
workspace members. Server enforces this on every read.

---

## 7. Messages / Nodes + Streaming send (M2) `[partial impl]`

A conversation's history is an append-only tree of **nodes** (`role` =
`user|assistant|system`), ordered by `seq` within a branch and linked by
`parent_id` (the fork spine — see §9).

**Node** `{ "id", "branch_id", "parent_id", "seq", "author_id", "role", "content", "token_count", "created_at" }`

`GET /api/workspaces/{wid}/conversations/{cid}/branches/{bid}/nodes`
→ `{ items: Node[] }` (ordered).

### Send a prompt (SSE stream) `[impl: /chat/stream is the stub of this]`
`POST /api/workspaces/{wid}/conversations/{cid}/branches/{bid}/messages`
```json
// req
{ "content": "Why is retrieval returning stale chunks?" }
```
Response: `200 text/event-stream`. The server persists the user node, then
streams the assistant reply and persists it on `[DONE]`. SSE frames:
```
data: {"type":"user_node","node":{...}}

data: {"type":"token","text":"Because "}
data: {"type":"token","text":"the "}
...
data: {"type":"assistant_node","node":{...}}      // final persisted node
data: [DONE]
```
The same events are **also** broadcast to the workspace WS room (§11) so other
members see the live stream. Observers get `403`.

---

## 8. Prompt Library (M5)

**Prompt** `{ "id", "workspace_id", "author_id", "title", "body", "tags": [], "created_at" }`

| Method | Path | Body / Notes | Returns |
|---|---|---|---|
| `GET`  | `/api/workspaces/{wid}/prompts` | `?q=` (search title/body/tags) | `{ items: Prompt[] }` |
| `POST` | `/api/workspaces/{wid}/prompts` | `{ "title", "body", "tags" }` | `201 Prompt` |
| `PATCH`| `/api/workspaces/{wid}/prompts/{pid}` | partial | `Prompt` |
| `DELETE`| `/api/workspaces/{wid}/prompts/{pid}` | | `204` |

Insertion into a conversation is a client concern (paste `body` into the
composer) — no special endpoint.

---

## 9. Fork & Branch Tree (M4)

**Branch**
```json
{ "id", "conversation_id", "name", "parent_branch_id",
  "fork_node_id", "head_node_id", "engine_thread_id": null, "created_at" }
```

**Fork = O(1):** new `branch` row pointing at `fork_node_id`; no history copied
(structural sharing via the `parent_id` walk). For a **deep-reasoning** branch
the server also copies the LangGraph checkpoint to a fresh `engine_thread_id`.

| Method | Path | Body / Notes | Returns |
|---|---|---|---|
| `GET`  | `/api/workspaces/{wid}/conversations/{cid}/branches` | the branch tree | `{ items: Branch[] }` |
| `POST` | `/api/workspaces/{wid}/conversations/{cid}/branches` | `{ "from_node_id", "name" }` | `201 Branch` |

Both branches continue independently; the client renders `parent_branch_id`
links as the Git-style tree.

---

## 10. History, Replay & Export (M8)

`GET …/branches/{bid}/replay` → ordered nodes from root → head for step-through
playback: `{ "branch_id", "nodes": Node[] }`.

`GET …/conversations/{cid}/export?format=json|md&branch={bid}`
→ `200`; `application/json` or `text/markdown` (attachment). JSON ships first;
Markdown is a cut-line per the plan.

---

## 11. Realtime — WebSocket (M3, presence + broadcast)

**Connect:** `GET /ws/workspaces/{wid}?token=<JWT>` (token in query — browsers
can't set headers on WS). One room per workspace. Server validates membership
on connect, closes `4403` if not a member.

**Server → client events** (`{ "type", ... }`):
```json
{ "type": "presence",     "members": [{ "user_id", "email", "online": true }] }
{ "type": "user_joined",  "user_id", "email" }
{ "type": "user_left",    "user_id" }
{ "type": "message",      "conversation_id", "branch_id", "node": { ... } }   // mirrors §7 user_node/assistant_node
{ "type": "token",        "conversation_id", "branch_id", "text" }            // live stream fan-out
{ "type": "branch_created","conversation_id", "branch": { ... } }
{ "type": "run_event",    "run_id", "event": { ... } }                        // §13 monitor frames
```
**Client → server events:** `{ "type": "ping" }` (heartbeat) — sends/forks go
through REST/SSE, not the socket, to keep an authoritative server order.

Ordering guarantee: the server stamps every persisted node with a monotonic
`seq`; clients render by `seq`, not arrival time.

---

## 12. Deep Reasoning — Runs (M6)

Escalates a branch from plain chat to the recursive engine.

**Run** `{ "id", "workspace_id", "conversation_id", "branch_id", "status": "running|paused|done|killed|error", "provider", "model", "stop_reason", "started_at", "ended_at" }`

| Method | Path | Body / Notes | Returns |
|---|---|---|---|
| `POST` | `…/branches/{bid}/runs` | `{ "prompt", "config"? }` → start a run | `201 Run` |
| `GET`  | `/api/workspaces/{wid}/runs/{rid}` | | `Run` |
| `POST` | `/api/workspaces/{wid}/runs/{rid}/steer` | `{ "instruction" }` (M9-gated) | `202` |
| `POST` | `/api/workspaces/{wid}/runs/{rid}/kill` | stop mid-loop (M9-gated) | `202` |
| `GET`  | `/api/workspaces/{wid}/runs/{rid}/steps` | persisted trace (replay) | `{ items: RunStep[] }` |

Live trace arrives over the WS room as `run_event` frames (§11), not by polling.

---

## 13. Monitor frames (M7) — the `run_event.event` payloads

Normalised from the engine's `step`/`token`/`complete` stream:
```json
{ "kind": "step",     "idx", "node", "depth", "energy", "loop_guard", "payload": {...}, "latency_ms" }
{ "kind": "token",    "text" }
{ "kind": "budget",   "tokens_used", "tokens_budget", "pct" }     // drives the budget meter; alert at threshold
{ "kind": "waiting",  "reason": "steer" }                          // run paused for human input
{ "kind": "complete", "stop_reason", "status": "done|killed|error" }
```
The monitor dashboard renders: reasoning topology (`step` nodes + `depth`), the
energy/loop_guard gauges, the **budget meter** (`budget.pct`), and the
**kill/steer** controls (→ §12).

---

## 14. Build status

| Area | Status |
|---|---|
| `GET /health` (3-tier proof) | ✅ implemented |
| §4 Auth — register / login / me (JWT, bcrypt) | ✅ implemented |
| §5 Workspaces — create/list/get, members, role patch | ✅ implemented |
| §5 Invites — create / preview / accept | ✅ implemented |
| §2 RBAC — `require_role` gating + member-rank ladder | ✅ implemented |
| `POST /chat/stream` (SSE, stub provider) | ✅ implemented (becomes §7) |
| Pluggable provider (stub/groq/ollama) | ✅ implemented |
| §6–§13 (conversations, fork, prompts, runs, WS) | 📋 contract agreed, not built |

> **Next to implement (M2):** §6 conversations + §7 — upgrade the bare
> `/chat/stream` stub into the persisted, workspace-scoped, branch-aware streaming
> message endpoint; then the §11 WebSocket room (presence + fan-out, M3).

_Contract v0.1 — change it freely as the build teaches us; keep this file the
single source of truth for the wire format._
