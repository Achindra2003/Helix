# AI Lane — Integration Contracts

The AI side of Helix is complete on `ui-standout` (July 6, five commits:
`351137c` → `bd0b95e`, 177/177 tests). This document is the handoff: exactly
what the **frontend** and **DB/backend** lanes build against, what is
deliberately left as a seam, and the rituals that keep the AI layer honest.

Companions: `HELIX-AI-EXPLAINED.md` (how the engine thinks),
`LAUNCH-PLAN.md` (why these features), `MARKET-VALIDATION.md` (the gaps they
close).

---

## 1. What the AI lane now provides

| Capability | Where | The one-line story |
|---|---|---|
| Provider resilience | `api/providers/resilient.py` | Retry-with-backoff before first token, per-endpoint circuit breaker, safe fallback to the server provider; mid-stream failures degrade honestly |
| Capability registry | `api/providers/capabilities.py` | `capabilities(model)` → context window / JSON mode / tools; code asks, never assumes |
| Durable deep runs | `api/conversation/runs.py` | Runs execute server-side; disconnect ≠ death; reconnect, status, kill, per-workspace queue |
| Retrieval substrate | `api/conversation/embeddings.py` | Every node embedded once (versioned rows); semantic recall reads persisted vectors |
| File grounding (RAG) | `api/documents/` | Workspace knowledge base: upload → chunks+vectors; chat turns ground with citations when relevance clears a measured floor |
| Provenance | `deep_runs.model/.provenance` | Every run stamps what produced it (model, thresholds, embedder, key source) |
| Injection regressions | `tests/test_injection_regressions.py` | Attack corpus over every untrusted surface, structural assertions, runs every commit |
| Eval instruments | `backend/evals/` | Harness + hard question set + confidence-calibration readout |

---

## 2. Frontend contracts (Rajnish's lane)

### 2.1 New stream event kinds

All SSE frames and WS `run_event` relays share one shape: `{kind, ...}`.
Unknown kinds must be ignored (they already are in `ChatView`'s else-if
chains). Three new kinds:

```jsonc
// 1. Every deep run's FIRST frame (previously steerable-only).
{"kind": "deep_run", "run_id": "abc123"}

// 2. The run is waiting behind others in this workspace (concurrency cap).
//    The stream stays open; the run starts automatically. Show
//    "queued (position N)" instead of a mystery stall.
{"kind": "queued", "position": 1}

// 3. Chat grounding citations — emitted BEFORE the reply's tokens whenever
//    workspace documents cleared the relevance gate. Render "grounded on
//    spec.pdf §3"-style chips above/below the reply.
{"kind": "grounding", "items": [{
    "document_id": "…", "filename": "spec.md", "chunk_index": 2,
    "score": 0.41, "excerpt": "first 200 chars of the grounded chunk…"
}]}
```

### 2.2 Deep-run control endpoints

| Route | Who | What |
|---|---|---|
| `GET /conversations/deep/runs/{id}/stream?after=N` | any member who can read the conversation | Replay the event log from seq N, then follow live. **This is the reconnect path** — call it on page reload / tab restore with the last seen seq (or 0). |
| `GET /conversations/deep/runs/{id}/status` | same | `{run_id, status, seq, queue_position}` — status ∈ queued/running/paused/done/error/killed |
| `POST /conversations/deep/runs/{id}/kill` | Collaborator+ | Stops the run (cooperative). Closing the SSE **no longer stops a run** — a stop button should call this. |
| `POST /conversations/deep/runs/{id}/steer` | Collaborator+ | Unchanged semantics; streams the continuation segment. |

UI to build: reconnect-on-load for in-flight runs (keep `run_id` + last seq in
state), a queue indicator, an explicit stop button, citation chips, and the
**Documents panel** below.

### 2.3 Documents (knowledge base) endpoints

| Route | Who | Notes |
|---|---|---|
| `POST /api/workspaces/{wid}/documents` (multipart `file`) | Collaborator+ | Returns immediately with `status:"processing"` — poll list/detail until `ready`/`error`. 413 over 8 MB. txt/md/code/PDF. |
| `GET /api/workspaces/{wid}/documents` | any member | `{items:[{id, filename, status, error, chunk_count, …}]}` |
| `GET /api/workspaces/{wid}/documents/{id}` | any member | Detail incl. `error` reason |
| `DELETE /api/workspaces/{wid}/documents/{id}` | uploader or owner | Grounding stops citing it on the next send |
| `POST /api/workspaces/{wid}/documents/search` `{query, k}` | any member | Same ranking chat uses — build a "search the knowledge base" surface with it |

Grounding is automatic and workspace-wide: there is no per-conversation
attach step. A document that isn't relevant to a question stays out
(measured floor, see `grounding_floor` in config).

## 3. DB/backend contracts (Mansoor's lane)

### 3.1 New tables & columns (created automatically)

- `node_embeddings(node_id PK, version, vector BLOB, created_at)` — one row
  per node under the *current* embedder; overwritten on embedder upgrade.
- `documents(...)`, `document_chunks(...)` — see `api/documents/models.py`;
  chunk rows carry their own `embedder_version` + `vector`.
- `deep_runs` gains `model` (str) and `provenance` (JSON text). Old rows read
  NULL — treat as optional.

Schema evolution today = `create_all` + the forward-only column shim in
`api/db.py` (`_add_missing_columns`). **The Alembic migration baseline for
the hosted instance is your lane**; the shim is deliberately minimal and
SQLite/Postgres-safe until then.

### 3.2 Seams deliberately left open (labeled, not blocking)

1. **Original-file blob store.** Ingestion keeps extracted text only;
   re-upload = re-ingest. If file download matters, add a blob store behind
   the upload endpoint — nothing in the AI lane reads raw bytes after ingest.
2. **pgvector escape hatch.** Vectors are packed float32 in ordinary
   columns; Python cosine is fine to ~10⁵ chunks/workspace. Past that, swap
   `DocumentIndex._workspace_chunks` + scoring for a pgvector query — the
   call sites are two methods.
3. **Restart-surviving deep runs.** Run handles are in-process (like the WS
   rooms). The seam: LangGraph's sqlite checkpointer (`checkpointer=` param
   of `create_ouroboros_graph` — already exists) + persisting the run
   registry + rebuild-on-boot. The durable `deep_runs` row already preserves
   the evidence trail of any run that completed a segment.
4. **Redis fan-out** for multi-instance realtime: unchanged decision —
   documented, deferred, `roster()`/`broadcast()` is the narrow seam.

### 3.3 New config (all env-overridable, defaults sane for self-host)

```
llm_max_attempts=3  llm_breaker_threshold=4  llm_breaker_cooldown_s=30
llm_enable_server_fallback=true          # hosted BYO-key: no server key = no-op
deep_reasoning_deadline_s=300            # wall-clock cap per run segment
deep_runs_per_workspace=2                # concurrency cap; rest queue visibly
deep_run_retention_s=1800                # live handle retention after finish
document_max_bytes=8388608  document_max_chars=500000
grounding_k=4  grounding_floor=0.15  grounding_chunk_chars=1200
documents_ingest_inline=false            # true only in tests
```

---

## 4. Rituals (what keeps the AI layer honest)

- **Every commit:** full suite (`pytest -q`, hermetic — stub provider, no
  keys) includes the injection regression corpus and the eval harness's
  hermetic self-test.
- **Any model/prompt/threshold change:** re-run the eval before merging —
  `python -m evals.harness --limit 6 --arms fixed-1,fixed-4,adaptive`; the
  numbers go in `evals/results/`. The claim lives in `FINDINGS.md`; keep it
  measured, not asserted.
- **The next experiment (queued):** the hard set —
  `python -m evals.harness --questions evals/questions-hard.json` — the
  terrain where refinement can show a quality win over single-pass.
- **Periodically (free):** `python -m evals.calibration` over accumulated
  runs; add `--judge` for the judged calibration curve (spends tokens).
- **Provenance discipline:** never strip the `provenance` stamp from
  `deep_runs` writes — it's the attribution record every swap-debugging
  session will want.

## 5. Known limits, stated on purpose

- A **process restart** loses in-flight deep runs (their durable record rows
  remain). Single-instance deployment is the documented posture.
- Deep Reasoning still runs on **Groq-shaped providers only** (the engine
  builds a `ChatGroq` client); chat is fully provider-agnostic. Widening the
  deep path to any OpenAI-compatible endpoint is a contained change in
  `build_ouroboros_graph`.
- Grounding covers **chat turns**; deep-reasoning seeds don't retrieve from
  documents yet (`render_seed` is the place, `DocumentIndex.search` is the
  tool — a labeled future task).
- The eval verdict stands: *if you iterate, converge — don't count.* The
  quality-win claim for refinement awaits the hard-set run.
