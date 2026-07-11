# Helix as a GenAI Study Companion

A guided dissection: every industry LLM-engineering concept Helix implements,
mapped to the exact file and line where it lives — so revising the concepts
*is* reading the codebase, and interview questions map to code you wrote.
Each chapter lands alongside the phase that built it.

How to use it: read the concept, open the file, trace the call path with the
tests next to it. The tests are executable documentation — every claim here
has one.

---

## 1 · LLM Observability (OTel GenAI tracing + the usage ledger)

**The industry problem.** An LLM feature in production fails in ways normal
services don't: a reply is slow (which of the four retrieval steps + one model
call was it?), wrong (what context did the model actually see?), or expensive
(which workspace/model/feature is burning tokens?). The standard answer is
**span-level tracing** — every LLM call becomes a span with
[GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
attributes — plus a **durable usage ledger** for billing math, because traces
get sampled and billing can't be.

**Where it lives in Helix:**

| Concept | Where | What to notice |
|---|---|---|
| Tracer bootstrap, env-gated | `backend/api/telemetry.py` → `init_telemetry()` | No OTLP endpoint ⇒ *no SDK provider installed* ⇒ `trace.get_tracer` hands back a no-op. Observability is an overlay; the hermetic suite never talks to a network. |
| GenAI semconv span | `backend/api/conversation/producer.py` → `ChatProducer.run` | Span name `"chat {model}"`, attrs `gen_ai.system/request.model/usage.*`. Opened only around the provider stream — so span latency means *model* latency, not retrieval. Note the `try/finally`: the span ends even if the client abandons the generator mid-stream. |
| Retrieval spans | `documents/service.py` → `DocumentIndex.search`, `conversation/embeddings.py` → `EmbeddingIndex.rank` | Candidates/hits/floor/top-score as attributes — the numbers you need when someone asks "why didn't it ground?". |
| Provider-reported usage | `providers/groq.py`, `providers/ollama.py`, `providers/stub.py` | The *correct* way to count tokens is to not count them — ask the provider. Groq: `stream_options.include_usage` (final frame has usage and an **empty `choices`** — see the guard). Ollama: `prompt_eval_count`/`eval_count` on the done frame. Client-side "counting" (the old chunk count) is always wrong. |
| Usage through the fallback wrapper | `providers/resilient.py` → `last_usage` passthrough | If the primary died and the fallback served, whose usage is it? The wrapper answers: whoever actually streamed. |
| The accounting seam | `producer.py` → `UsageSink`, bound in `conversation/router.py` → `_usage_sink_for` | The producer stays workspace-ignorant; the router binds workspace identity. Same dependency-injection shape as `Recaller`/`Grounder`. |
| The ledger | `telemetry.py` → `LlmCallRow`, `record_llm_call` | Fire-and-forget: accounting must never slow or fail a reply. Traces answer "why slow", the ledger answers "what did this cost" — kept separate because sampling kills billing math. |
| Cost estimation | `providers/pricing.py` | Prefix-matched price table; unknown model ⇒ `None`, never an invented dollar figure. Surfaced at `GET /api/workspaces/{wid}/usage`. |

**LangChain/LangGraph callbacks — the deep-run half.** This is the part worth
studying closely for LangGraph itself:

- `backend/api/telemetry.py` → `LlmSpanHandler` (inside `_get_handler_cls`).
  LangChain fires lifecycle hooks around every model invocation:
  `on_chat_model_start` → the call begins (open a span, note the clock);
  `on_llm_end` → an `LLMResult` arrives (read usage, close the span, write
  the ledger); `on_llm_error` → record and close. Each hook receives a
  `run_id` correlating start/end — the handler keeps a dict of open spans
  keyed by it, because calls can interleave.
- **How the handler reaches every call:** `deep_reasoning.py` →
  `build_ouroboros_graph` puts it in `graph_config["callbacks"]`. LangGraph
  propagates the config's callbacks down into every node execution and every
  LLM invocation the graph makes — attach once at build, observe everything.
  The engine never learns tracing exists. (The engine's own
  `new_usage_handler` token counter rides the same mechanism — read
  `engine/ouroboros/usage.py` and compare.)
- **Where usage hides in an `LLMResult`:** `_extract_usage` shows both
  shapes — classic `llm_output["token_usage"]` and the newer
  `message.usage_metadata` on generations. Providers disagree; robust code
  checks both.
- Spans carry `helix.run_id`, so in Langfuse/Jaeger a whole deep run's
  reason→reflect→synthesize calls group together.

**Try it live:** run a self-hosted Langfuse (`docker compose` from their
repo), set in `backend/.env`:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64 of pk-lf-...:sk-lf-...>
```

then send a chat turn and a deep run and watch the spans arrive.

**Interview questions this chapter answers:**
- "How would you debug a slow/wrong LLM response in production?"
- "How do you attribute token spend across tenants when responses stream?"
- "Why not count tokens client-side?" (chunk ≠ token; the provider knows)
- "How do LangChain callbacks work, and how does LangGraph propagate them?"

**Tests to read:** `api/conversation/tests/test_telemetry.py` (in-memory span
exporter — note the proxy-tracer trick: set the global provider before any
span starts), `api/providers/tests/test_resilient.py::test_usage_passes_through…`.

---

## 2 · Measured RAG (retrieval evals, BM25, hybrid fusion)

**The industry problem.** Everyone wires RAG; almost nobody measures it. The
interview question is "how do you *know* your retrieval works?", and the only
good answer has three parts: a labeled dataset, ranking metrics, and a change
process where thresholds come from the data.

**The dataset:** `backend/evals/retrieval-golden.json` — 8 realistic team
documents, 12 positive queries labeled with their relevant document, 4
negatives that must retrieve *nothing*. Query kinds are deliberate:
`exact-term` (error codes, env-var names — where embeddings are weakest),
`paraphrase` (where they're strongest), and negatives (the relevance gate's
contract). Judgments are **document-level** so re-chunking never invalidates
labels — a real-world dataset-versioning lesson.

**The metrics:** `backend/evals/retrieval.py` — recall@1, recall@k, MRR
(1/rank of the first relevant hit), and **negative leakage** (fraction of
unrelated queries that retrieved anything; the target is exactly 0). Run it:
`python -m evals.retrieval` — the report lands in `evals/results/`.

**What measuring immediately caught** (the story to tell): the dense floor of
0.15, documented as "separates with margin", *leaked two negatives* — "best
pizza near the office" retrieved the pricing sheet at cosine 0.166. Plotting
the distributions showed the weakest positive at 0.241 and the strongest
negative at 0.181, so the floor moved to 0.20 (`api/config.py`, with the
measurement cited in the comment). One harness run, one real calibration bug,
zero vibes. Post-fix: hybrid scores recall@1 = 1.00, MRR = 1.00, leakage = 0.

**BM25, from scratch:** `backend/api/documents/lexical.py` (~60 lines —
readable beats imported at this scale). Things to actually understand:
- **idf** discounts common terms; the +0.5-smoothed variant never quite hits
  zero for ubiquitous words, so the *gate* relies on the squash gap, not
  literal zero (see `test_hybrid.py::test_bm25_ranks_rare_term…`).
- **tf saturation** (`k1`): the 5th occurrence of a term adds less than the
  1st. **Length normalization** (`b`): long chunks don't win by volume.
- **Tokenization keeps identifiers whole** (`retry_count`, `ZX-9931`, `v1.2`)
  — exact-term matching is the entire reason lexical exists.
- **Corpus-size sensitivity**: with 2 documents, idf is nearly flat and no
  threshold separates anything — why the unit tests pad the corpus, and why
  the squash constant (`half=5`) is sized to workspace-scale corpora.

**Hybrid fusion:** `DocumentIndex.search` (`documents/service.py`) — dense
and BM25 each rank; **RRF** (`rrf_fuse`, k=60) merges by *position* because
cosine and BM25 scores live on incomparable scales; the eligibility gate
admits a chunk if *either* signal clears its floor. The canonical failure
each side covers: dense catches "how do we undo a bad release" (the runbook
never says "undo"); lexical catches "what does ERR-5093 mean" when the
embedding of an error code carries no signal —
`test_hybrid.py::test_hybrid_rescues_the_exact_term_dense_misses` constructs
exactly that with a scripted embedder, so the rescue is a proven property,
not an anecdote.

**Interview questions this chapter answers:**
- "How do you evaluate retrieval quality?" (golden set, recall@k/MRR,
  negatives as a first-class metric)
- "Dense vs sparse retrieval — when does each fail?" (paraphrase vs
  exact-term, with a constructed counterexample each)
- "Why RRF instead of score interpolation?" (incomparable scales; ranks
  are scale-free)
- "How do you pick a similarity threshold?" (measure the two distributions,
  split where the margin is; re-run the harness on every retrieval change)

**Tests to read:** `api/documents/tests/test_hybrid.py`,
`evals/test_retrieval_hermetic.py` (note: the lexical arm is asserted
hermetically because BM25 is embedder-independent — the dense arm's numbers
only mean anything under the real embedder).
