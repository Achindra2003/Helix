# Helix — The AI / GenAI Lane

A technical account of the intelligence layer: how Helix invokes language models,
constructs context, reasons deeply, grounds on documents, uses tools, and
remembers — with the mechanism ("how"), the design rationale ("why"), and an
honest evaluation of each part.

**Scope note.** "Shared workspace" is the *product frame*, not the technical
contribution. The substance of this lane is: (a) a uniform streaming/inference
pipeline, (b) an adaptive, convergence-controlled reasoning engine, (c) measured
retrieval, and (d) a governed tool loop. Those are what the sections below cover.

---

## 0. Architecture at a glance

Every model-backed reply — plain chat, deep reasoning, agentic — flows through
**one orchestrator** (`engine.send`) driving a swappable **producer**. The
producer emits *content events*; the engine brackets them with *persistence and
relay events*. So streaming, storage, permissions, and real-time fan-out are
implemented once and inherited by every mode.

```
engine.send(branch, input):
    persist user message                      -> UserNode event
    producer.run(history) --> [Token|Step|Grounding|ToolCall|...]  (relayed live)
    persist assistant message                 -> AssistantNode event
    emit Done
```

Three producers implement the same interface: `ChatProducer`,
`DeepReasoningProducer`, `AgentProducer`.

---

## 1. The provider abstraction (model seam)

**What it is.** A single interface, `LLMProvider.stream_messages(messages) ->
async iterator of tokens`, with interchangeable implementations.

**How it works.** Each provider is an async generator yielding token deltas, so
the whole stack is streaming end-to-end. Three implementations exist:
- **Groq** — hosted OpenAI-style API; chat uses an ~8B model, deep reasoning an
  ~70B model.
- **Ollama** — local inference for self-hosting.
- **Stub** — deterministic canned output, no network.

Which provider serves a call is decided per workspace by a pure resolver:
workspace settings (a BYO encrypted key) take precedence, else the server's
`.env`. A resilience wrapper retries a rate-limited provider and can fall back
to the server provider; usage is always attributed to whoever actually streamed.

**Design rationale.** The adapter pattern means changing vendor is a one-file
change. Splitting chat (fast/cheap) from deep reasoning (large/slow) matches
compute to task. The stub is why **261 tests run offline with no API key** —
correctness is verified hermetically.

---

## 2. Context construction (what the model sees)

**What it is.** The prompt assembled before every turn.

**How it works.** A context builder composes four sources into the message list:
1. **Branch history** — the current branch's ancestor turns as real chat turns.
2. **Referenced conversations** — linked threads, resolved live and folded into
   a system frame.
3. **Semantic recall** — older, currently-elided turns from this thread that are
   relevant to the new question, retrieved by embedding similarity.
4. **Document grounding** — top document chunks above the relevance floor (§7).

The whole prompt is **token-budgeted**: history and recall are selected to fit a
budget, degrading to recency if retrieval fails (recall is an enhancement, never
a failed send). Sources 2–4 are third-party text, so they are enclosed in a
`<quoted-context>` boundary marked *data, not instructions*; an adversarial test
suite verifies injection attempts inside that boundary are ignored.

**Design rationale.** The "shared brain" is not a special subsystem — it is this
context assembly over a shared store, plus a system prompt that identifies the
assistant as one shared voice and tags each turn with its author (`[alice] …`).
The model reasons over *real retrieved messages*, not invented history, which is
what makes team continuity work without fabrication.

---

## 3. Chat producer (single-pass reply)

**What it is.** The default reply path.

**How it works.** `ChatProducer` streams provider tokens straight through as
`Token` events; the engine accumulates them, persists the final assistant node,
and attaches token/provider metadata. A producer crash is caught, a clean
terminal event emitted, and the partial reply persisted — the client never sees a
torn stream.

**Design rationale.** Most questions are answered best (and cheapest) in one
pass; deep reasoning is an explicit escalation, not the default (§5).

---

## 4. Deep Reasoning — the Ouroboros engine

**What it is.** An iterative reasoning process that critiques and refines its own
answer until it stops improving. Implemented as a LangGraph state machine, not a
counting loop.

**How it works.** The graph:

```
ingest -> think -> reflect --+--> emotional --+
                             +--> logical  ---+--> synthesize --(route)--> think
                             +--> memory   ---+        |
                                                       +--> plan_research -> workers -> think
                                                       +--> surface -> remember -> breathe -> (steer?) -> END
```

- **think** generates the next thought from recent context + stored insights.
- **reflect** fans out to three *parallel* perspectives (emotional / logical /
  memory); **synthesize** fans them back in. Synthesize does not free-associate:
  it **critiques and rewrites the current best answer to the original question**,
  anchored to that question so it cannot drift, and emits a self-confidence
  score.
- **plan_research → workers** is a map-reduce fan-out for sub-questions.
- **surface** is the only node whose tokens stream to the user; it runs a
  *humanising* pass. Crucially, convergence is measured on the terse internal
  synthesis, not the humanised text, so presentation never corrupts the halting
  signal.
- The graph checkpoints between cycles; `interrupt` enables human-in-the-loop
  steering (§6, §5-guided).

**Design rationale.** A real graph (parallelism, map-reduce, checkpointing,
interrupts) makes the reasoning *inspectable and steerable*, which is the point —
see the honest evaluation in §12.

---

## 5. The convergence controller (the stopping rule)

**What it is.** The decision procedure for when to stop iterating — the
project's core research idea.

**How it works.** After each cycle, `decide()` reads two cheap signals:
- **Answer stability** — cosine similarity between successive refined answers,
  using sentence embeddings. The threshold **auto-calibrates** to the embedder
  (~0.90 for neural MiniLM, ~0.78 for the lexical fallback), because neural
  cosines run far hotter than token-overlap scores. Long answers are
  **chunk-embedded and mean-pooled** (MiniLM truncates at 256 tokens, so an
  untreated contradiction past the cutoff once scored 1.0000 similarity), and the
  pooled score is blended with a **least-anchored-sentence floor** so a single
  flipped conclusion buys another cycle.
- **Self-confidence** — the synthesizer's own 0–1 estimate, parsed with a repair
  pass and *flagged as unreported if missing*, so a missing rating can never
  satisfy the gate.

It halts on: hard budget exhausted, **or** stable **and** confident. The key
case: **stable-but-unconfident** is what a *stuck* loop looks like, so it triggers
**perturb-on-stall** — the next cycle attacks the answer's weakest assumption,
and only convergence *after* the challenge counts. Design maxim: *repetition is
weak evidence; surviving an attack is real evidence.* A transient provider error
now halts with its own `provider_error` reason instead of masquerading as
convergence (a 429 used to keep the previous answer, making `stability(prev,
prev)=1.0` look like "done").

**Design rationale.** This is *adaptive test-time compute*: spend proportional to
how unstable the answer still is, with a principled — not fixed — stop.

---

## 6. Durable, steerable runs

**What it is.** Deep runs that survive a closed tab and accept mid-run guidance.

**How it works.** A run executes as a **server-side task appending to a per-run
event log**; it does not live inside the HTTP request. A client's SSE stream is a
*subscriber* that reconnects with `?after=N` and replays missed events, then
follows live. Guided runs pause at a graph checkpoint (`interrupt_before`); a
collaborator posts steer text over HTTP, and the run resumes from the checkpoint
(via `aupdate_state`). Budget is enforced twice — a compute budget and a
wall-clock deadline per segment — and a per-workspace concurrency cap queues
excess runs.

**Design rationale.** Decoupling the run from the request is what makes minutes-
long reasoning practical and collaborative. *Limitation:* the live run handle is
in-process, so a **server restart** (not a closed tab) loses an in-flight run;
the durable record survives.

---

## 7. Retrieval-augmented generation (document grounding)

**What it is.** Answering from uploaded documents, with citations.

**How it works — pipeline.**
1. **Ingest.** 8 MB cap, extension allowlist, text extracted (pypdf for PDFs);
   original bytes are discarded — only extracted text is kept.
2. **Chunk.** ~800 characters with ~15% overlap so ideas aren't cut mid-thought;
   judgments in the eval set are document-level so re-chunking never invalidates
   labels.
3. **Embed.** `all-MiniLM-L6-v2`, stored as **packed float32 in an ordinary DB
   column** (identical on SQLite and Postgres) — deliberately **no vector
   database**, with a stated revisit threshold (~10⁵ chunks).
4. **Retrieve — hybrid.** Dense cosine similarity **and** a from-scratch **BM25**
   lexical index, fused by **Reciprocal Rank Fusion** (k=60) because cosine and
   BM25 live on incomparable scales.
5. **Gate.** A relevance floor of **0.20**; below it nothing is injected, so
   unrelated questions correctly receive no citation.

**How it works — evaluation.** A labelled golden set (8 docs, 12 positive
queries, 4 negatives-must-return-nothing) scored on **recall@1, recall@k, MRR,
and negative leakage**. The 0.20 floor was *derived from data*: the original 0.15
leaked two negatives (a pizza query pulled a pricing sheet at cosine 0.166);
plotting distributions put the weakest positive at 0.241 and strongest negative
at 0.181, so the floor moved to 0.20 (post-fix: recall@1 = 1.00, MRR = 1.00,
leakage = 0).

**Design rationale.** Hybrid retrieval because dense catches paraphrase and
lexical catches exact tokens (error codes, IDs) whose embeddings carry no signal;
a proven property, tested with a scripted embedder. Grounding applies to both
chat and deep runs and enters inside the same `<quoted-context>` boundary, so
injection defenses cover documents automatically.

---

## 8. Agent mode (governed tool use)

**What it is.** The model may call tools (search knowledge base, search
conversations, web search) before answering, under three governance layers.

**How it works.** A LangGraph tool loop:

```
START -> agent --(no tool calls)--------> END
           | (sensitive)      | (safe)
           v                  v
   [interrupt] gate --(approved)--> tools -> agent
           +--(denied: denial ToolMessages)--> agent
```

Governance is enforced *structurally*, not by prompt text:
- **Catalog** — what tools exist (`tools/builtin.py`).
- **Allowlist** — what the workspace permits (`WorkspaceSettings.tool_allowlist`,
  owner-managed; `""` = safe internal default, `"[]"` = deliberately tool-less —
  absence ≠ emptiness).
- **Approval** — sensitive calls pause at `interrupt_before=["gate"]`; a
  collaborator approves/denies; resume via `aupdate_state`.

The load-bearing detail: `bindable()` filters catalog × allowlist × availability
**before `bind_tools`**, so an un-allowed tool is *never offered to the model* —
a door it never learns exists, not a locked one. Routing is **state-shaped**
(`route_gate` reads the messages, not a flag); the `add_messages` reducer appends
so the model reads its own tool results; termination is a `recursion_limit` from
`agent_max_tool_rounds` (with a `test_runaway_tool_loop_hits_the_recursion_limit`).
Failures degrade, never crash: a broken tool returns its error as the tool
result ("the search failed, but…"); denials fold back "answer from what you have
and say what you couldn't check." Security is *inherited*: `search_conversations`
runs as the caller (`viewer_id` flows into the same visibility clause as the
search endpoint), so the agent can never surface a private thread.

**Design rationale.** Prompt-based safety is a suggestion; structural safety
(binding decisions, graph shape) is a guarantee.

---

## 9. Memory and proactive resurfacing

**What it is.** The workspace remembers prior reasoning and surfaces it while you
type.

**How it works — write side.** Every persisted node fires a background embed into
`NodeEmbeddingRow` (packed float32), each node embedded exactly once, **versioned
by embedder name** — so upgrading the embedder is a *lazy re-embed*, never a
migration, and a lost background task is harmless (retrieval backfills).

**How it works — read side.** While typing, the client debounces 700 ms, guards
with a sequence counter (discarding superseded responses), and posts the draft to
a search that runs one SQL join `Node → Branch → Conversation` carrying the same
**visibility clause** as thread listing (a private thread can never resurface for
a non-author). Cosine similarity is computed in Python over the candidates; the
server floor is **0.15**, but the client raises it to **0.33**, drops the current
thread, and keeps one chip per conversation (max three) — a *stricter* bar
because this surface is *unsolicited* (a wrong chip is noise, unlike a mediocre
result in a search you asked for).

**Design rationale.** One substrate, four surfaces (resurfacing strip, Ctrl-K
search, the agent's `search_conversations`, and chat's recall block) — all
inheriting the same visibility guarantee.

---

## 10. Observability and cost accounting

**What it is.** Per-call usage and tracing.

**How it works.** Every provider call reports `(model, tokens, latency)` through a
`UsageSink` bound per workspace, landing in `llm_calls`. Token counts come from
the *provider* (Groq `stream_options.include_usage`, guarded because the final
usage frame has an empty `choices` array; Ollama `prompt_eval_count`/`eval_count`)
— never by counting chunks, since a chunk is not a token. OpenTelemetry spans wrap
only the provider stream (so span latency = model latency), inside a
`try/finally` so the span closes even if the client abandons the generator; with
no OTLP endpoint configured the tracer is a no-op, keeping tests hermetic. The
tracing callback is attached once to the graph config and LangGraph propagates it
into every node.

---

## 11. Testing strategy

The stub provider + a stub embedder make the entire lane deterministic and
offline. **261 tests** cover streaming, persistence, RBAC, convergence halting,
retrieval metrics, the injection boundary, tool governance, and the recursion
limit — no network, no key.

---

## 12. Evaluation and honest positioning

**Method.** Three arms (single-pass, adaptive/Ouroboros, blind fixed-4), blind
LLM judge, on two question sets.

**Results.**
- *Pilot (18 easy questions):* single-pass won outright (8.83 vs 8.17). On
  questions a 70B already handles, extra refinement dilutes more than it deepens.
- *Hard set (8 questions engineered so single-pass plausibly fails):* single-pass
  **8.75**, adaptive **8.63** (converged 8/8 at ~half the tokens of fixed-4),
  fixed-4 **8.13** (worst and most expensive). Adaptive won *outright* on the two
  **interacting-constraints** questions, where a single pass commits early and
  misses a trade-off.

**Honest claim.** Ouroboros is **not** a higher-quality-on-average engine. Its
value is: (1) **adaptive cost** — it matches the fixed-iteration methods people
actually use for hard problems at ~half the tokens, and converges in one pass on
easy ones; (2) **transparency** — inspectable reasoning; (3) **steerability** —
human-in-the-loop mid-run; (4) a genuine **quality win on tangled, multi-
constraint problems**. The measured finding — *single-pass usually wins; cycle
spend tracks answer instability, not question difficulty* — is a legitimate
empirical result, and the reason Deep Reasoning is an **opt-in escalation**, not
the default.

**Known limitations (stated deliberately).** Energy/mood meters are interpretable
telemetry, not measured signals; self-confidence is mitigated but not formally
calibrated; a server-process restart loses an in-flight run's live handle.
