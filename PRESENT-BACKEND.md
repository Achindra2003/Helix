# Helix — The Backend / Infrastructure Lane

A technical account of the server: API design, data model, identity &
authorization, real-time transport, run durability, and the engineering that
makes Helix deployable and secure — with the mechanism ("how") and design
rationale ("why").

**Countable inventory:** **15 tables**, **68 HTTP routes** + one WebSocket
endpoint, **261 tests**.

---

## 0. Architecture at a glance

A **FastAPI** (async Python) service. Its organising principle is a **single
orchestrator**, `engine.send`, through which every AI reply flows. It persists
the user turn, runs a swappable *producer*, persists the assistant turn, and
streams the whole thing out — so persistence, authorization, streaming, and
real-time relay are written once and inherited by chat, deep reasoning, and agent
modes alike.

---

## 1. Authentication

**What it is.** Password login issuing a stateless session token.

**How it works.** Registration stores a **bcrypt** hash (one-way; the plaintext
is never persisted). Login verifies the hash and mints a **JWT** signed with the
server secret. The client sends the token as a bearer header on every request; a
FastAPI dependency, `get_current_user`, verifies the signature and resolves the
user. **Identity is derived only from the verified token** — there is no code
path that trusts a client-supplied user id.

**Design rationale.** Stateless JWTs need no server-side session store; deriving
identity solely from the signed token removes impersonation as a class of bug.

---

## 2. Authorization (RBAC)

**What it is.** Role-based access control per workspace.

**How it works.** Membership carries one role on a ladder: **owner ⊃ collaborator
⊃ observer**. A capability check (`can(role, action)`) gates each route: reads
need any membership, writes need collaborator+, settings need owner. Two
deliberate properties:
- **404, not 403** for non-members — returning "forbidden" would confirm a
  resource exists (an information leak); "not found" reveals nothing, so
  outsiders cannot even probe.
- **Server-enforced, UI-mirrored** — the client greys out disallowed controls as
  a courtesy, but the server independently rejects the action; a raw `curl` is
  refused identically.

---

## 3. Multi-tenancy & the data model

**What it is.** Hard isolation between workspaces, over a small relational schema.

**How it works.** A **workspace** is the tenant boundary; every query for tenant
data carries a visibility/membership clause. The **15 tables**:

| Group | Tables |
|---|---|
| Identity | `users`, `workspaces`, `memberships`, `invites` |
| Conversation tree | `conversations`, `branches`, `nodes`, `conversation_references` |
| Knowledge / memory | `documents`, `document_chunks`, `node_embeddings` |
| Config & runs | `workspace_settings`, `deep_runs`, `llm_calls`, `prompts` |

The conversation model is a tree: **Conversation → Branch → Node** (a Node is one
message). Embeddings are stored as packed float32 in `node_embeddings` /
`document_chunks`, versioned by embedder name.

**Design rationale.** A plain relational schema (no bespoke stores) keeps the
system portable between SQLite and Postgres and easy to reason about.

---

## 4. Branching: O(1) forks via structural sharing

**What it is.** Forking a conversation without copying its history.

**How it works.** A fork inserts **one branch row** whose `fork_node_id` points at
the divergence node. **Nothing is copied.** History is derived at *read* time by
walking `parent_id` up the ancestor spine, and the walk transparently crosses from
the child branch into the parent branch's nodes. Forking a 500-node thread and a
2-node thread both cost one insert; the read cost is the spine walk.

**Design rationale.** This is Git's structural sharing. It makes branching cheap
and gives the exact semantic teams need: a fork inherits its ancestors' context
and *nothing* from sibling branches, so two people explore two directions without
contaminating each other.

---

## 5. Cross-conversation references

**What it is.** Pulling another thread's *live* context into this one.

**How it works.** A reference is a single directed edge (`conversation_references`).
On every turn, the server re-reads the linked thread's *current* history and folds
it into a system frame, then discards it — nothing is persisted into the
referencing thread. References are resolved fresh per turn (so they stay in sync),
folded as background (so they never pollute lineage), and **not recursive** (B
reads A's messages, not A's links), so links cannot loop.

**Design rationale.** Distinct from forking: fork = inherit-and-diverge inside one
tree; reference = read another tree's live context from your own.

---

## 6. Real-time transport (the workspace room)

**What it is.** One WebSocket per workspace carrying presence and live fan-out.

**How it works.** Endpoint `/ws/workspaces/{id}?token=<jwt>` (the token rides the
query string because browsers cannot set custom headers on WebSocket handshakes;
it is verified identically to a bearer header). The server holds an **in-process
room dict**: joins/leaves broadcast the roster (deduplicated per user across
tabs) and track which branch each member is viewing. The **sender is excluded**
from its own broadcasts (its SSE already carries the change), and dead sockets are
dropped without breaking the sender. Only two functions sit above the room —
`broadcast()` and `roster()`.

**Design rationale.** Single-instance is **by design**, and the seam is
documented: because only those two functions touch the room, scaling to multiple
servers means swapping in Redis pub/sub in *one* module. This is also *why the
hosting target is an always-on VM rather than scale-to-zero* — a sleeping process
would drop every live room. (A decision with a stated reason.)

---

## 7. Durable, resumable runs

**What it is.** Deep/agent runs that outlive the HTTP request.

**How it works.** A run executes as a background task appending to a **per-run
event log**; clients subscribe over SSE and reconnect with `?after=N` to replay
missed events, then follow live. Budget is enforced twice (a compute budget and a
per-segment wall-clock deadline), and a **per-workspace concurrency cap** queues
excess runs rather than overloading the process. A durable `deep_runs` row records
each run.

**Design rationale.** Decoupling the run from the request is what makes
minutes-long, reconnectable, steerable reasoning possible. *Limitation:* the live
run handle is in-process, so a server restart loses an in-flight run (the durable
row survives as evidence).

---

## 8. Secure-by-default

**What it is.** The server refuses unsafe configuration.

**How it works.**
- **Boot check** (`secure_jwt_secret`): the app **refuses to start** if
  `JWT_SECRET` is still the public placeholder — that key signs every session, so
  a public default would let anyone forge a login. It prints a freshly generated
  secret, or `JWT_SECRET_FILE` can point at a writable path where one is generated
  and persisted (what the container does). `HELIX_DEV=1` skips the check for local
  development.
- **Rate limits** on sign-up, login, message send, run start, and upload.
- **Abuse caps** on workspaces, members, and invite uses.
- **Encryption:** BYO provider keys are encrypted at rest with a key **derived
  from the JWT secret** (which is why rotating the secret invalidates saved keys —
  documented so it's set before anyone is invited).

**Design rationale.** Security defaults that *fail closed* are the difference
between a demo and something safe to expose.

---

## 9. Packaging & deployment

**What it is.** A one-command install.

**How it works.** A **multi-stage Dockerfile** builds the frontend and serves it
from FastAPI in a single container: `git clone && docker compose up` → register at
`localhost:8000`. The container runs **non-root**, has a **healthcheck**, and
persists its database on a **named volume**; a separate compose file targets
**Postgres**. Real defects fixed en route: the Postgres URL needed the
`postgresql+asyncpg://` async driver, an unsatisfiable `pydantic-settings` pin,
and CUDA-torch bloat replaced by a CPU-only index (2.5 GB image).

---

## 10. Migrations & the hosted kit

- **Migrations (Alembic):** a baseline over the model files so a running instance
  can evolve its schema without data loss; `create_all` is kept for simple
  self-hosters.
- **Hosted kit:** an example starter workspace, password reset, an instance
  notice, and crash reporting — the extras a public instance needs.

---

## 11. Observability

Every provider call records `(model, tokens, latency)` into the `llm_calls`
ledger (kept separate from tracing because traces are sampled and billing cannot
be), served per workspace. OpenTelemetry spans wrap LLM and retrieval calls but
are a **no-op** unless an OTLP endpoint is configured, so tests never touch the
network.

---

## 12. Testing

**261 tests**, fully **hermetic** — the stub LLM provider and stub embedder mean
the whole backend (auth, RBAC, the conversation tree, streaming, run durability,
retrieval, tool governance) is verified with **no network and no API key**.

---

## Quick facts

- **FastAPI**, async; **15 tables**, **68 routes** + one WebSocket.
- Auth: bcrypt + JWT; identity only from the verified token.
- RBAC: **owner ⊃ collaborator ⊃ observer**; non-members get **404, not 403**.
- **O(1) forks** by structural sharing (Git-style); references are live edges.
- Realtime: in-process room behind two functions (Redis-swappable); always-on VM
  by design.
- Secure-by-default boot, rate limits, encryption; **one-command Docker**;
  Alembic; SQLite ↔ Postgres on the same code.
- **261 hermetic tests.**
