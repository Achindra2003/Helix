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
