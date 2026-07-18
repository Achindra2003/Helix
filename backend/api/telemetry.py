"""LLM observability — OpenTelemetry GenAI tracing + a durable usage ledger.

Two instruments, deliberately separate:

- **Spans** (OTel, GenAI semantic conventions): every LLM call — chat turns at
  the provider seam, each reasoning-cycle call inside a deep run (via a
  LangChain callback), and retrieval operations — becomes a span carrying
  `gen_ai.*` attributes (system, model, token usage). Export is *opt-in and
  env-gated*: with no OTLP endpoint configured there is no SDK provider, the
  API's no-op tracer takes over, and nothing leaves the process — the hermetic
  test suite and the zero-infra self-host story are untouched. Point
  `OTEL_EXPORTER_OTLP_ENDPOINT` at any OTLP/HTTP backend — a self-hosted
  Langfuse (`http://localhost:3000/api/public/otel`, with a Basic-auth header),
  Jaeger, or a collector — and every call becomes inspectable.

- **The ledger** (`llm_calls` table): spans are ephemeral and often sampled;
  billing questions ("what has this workspace actually spent?") need a durable,
  queryable record. One row per LLM call: kind (chat|deep), provider, model,
  real token usage as reported by the provider, latency. Written fire-and-
  forget — accounting must never slow or fail a reply.

Why both: traces answer "why was this call slow/wrong", the ledger answers
"what did this month cost". Industry stacks keep them separate for the same
reason (sampling kills billing math).
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from opentelemetry import trace
from sqlalchemy import Integer, String

from sqlalchemy.orm import Mapped, mapped_column

from .config import settings
from .db import Base
from .models import _now


def _uuid() -> str:
    return uuid4().hex


class LlmCallRow(Base):
    """One LLM call's accounting record (the usage ledger)."""

    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # chat | deep
    provider: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)


def init_telemetry() -> None:
    """Install an SDK tracer provider iff an OTLP endpoint is configured.

    Unconfigured (the default, and the test suite): no provider is installed,
    `trace.get_tracer` hands back the API's no-op tracer, and span calls cost
    nanoseconds. This function is the *only* place the SDK is touched.
    """
    if not settings.otel_exporter_otlp_endpoint:
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    headers = {}
    for pair in settings.otel_exporter_otlp_headers.split(","):
        if "=" in pair:
            key, _, value = pair.partition("=")
            headers[key.strip()] = value.strip()
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces",
                headers=headers or None,
            )
        )
    )
    trace.set_tracer_provider(provider)


def tracer() -> trace.Tracer:
    """The process tracer — resolved late so tests can install their own
    provider before the first span."""
    return trace.get_tracer("helix")


def set_usage_attributes(span: trace.Span, usage: dict | None) -> None:
    """Stamp GenAI-semconv token usage onto a span (no-op when unknown)."""
    if not usage:
        return
    if usage.get("input_tokens"):
        span.set_attribute("gen_ai.usage.input_tokens", int(usage["input_tokens"]))
    if usage.get("output_tokens"):
        span.set_attribute("gen_ai.usage.output_tokens", int(usage["output_tokens"]))


def record_llm_call(
    *,
    workspace_id: str,
    kind: str,
    provider: str,
    model: str,
    usage: dict | None,
    latency_ms: int,
) -> None:
    """Fire-and-forget ledger write. Accounting is an overlay: a lost row is
    a rounding error, a blocked or failed reply would be a product bug."""

    async def _write() -> None:
        try:
            from .db import SessionLocal

            async with SessionLocal() as session:
                session.add(
                    LlmCallRow(
                        workspace_id=workspace_id,
                        kind=kind,
                        provider=provider,
                        model=model,
                        input_tokens=int((usage or {}).get("input_tokens") or 0),
                        output_tokens=int((usage or {}).get("output_tokens") or 0),
                        latency_ms=latency_ms,
                    )
                )
                await session.commit()
        except Exception:
            pass

    try:
        asyncio.get_running_loop().create_task(_write())
    except RuntimeError:  # no loop (sync context) — skip, never block
        pass


def _extract_usage(response) -> dict | None:
    """Token usage from a LangChain LLMResult, wherever this provider put it."""
    out = getattr(response, "llm_output", None) or {}
    raw = out.get("token_usage") or out.get("usage") or {}
    if raw:
        return {
            "input_tokens": raw.get("prompt_tokens", 0),
            "output_tokens": raw.get("completion_tokens", 0),
        }
    # Newer LangChain: usage_metadata rides on the generation's message.
    for gens in getattr(response, "generations", []) or []:
        for gen in gens:
            meta = getattr(getattr(gen, "message", None), "usage_metadata", None)
            if meta:
                return {
                    "input_tokens": meta.get("input_tokens", 0),
                    "output_tokens": meta.get("output_tokens", 0),
                }
    return None


_handler_cls: type | None = None


def _get_handler_cls() -> type:
    """The LangChain-subclassed handler, defined lazily so the API layer never
    imports the LangChain stack unless a deep run actually happens (the same
    lazy-import rule `build_ouroboros_graph` follows)."""
    global _handler_cls
    if _handler_cls is not None:
        return _handler_cls

    from langchain_core.callbacks import BaseCallbackHandler

    class LlmSpanHandler(BaseCallbackHandler):
        """Every LLM call inside a deep run becomes a GenAI span + ledger row.

        LangGraph propagates the config's `callbacks` into every LLM
        invocation the graph makes, and LangChain fires `on_chat_model_start`
        / `on_llm_end` (or `_error`) around each — so one handler, attached
        once at graph build, observes every reason/reflect/synthesize call
        without the engine knowing tracing exists. Spans carry
        `helix.run_id` so a whole run groups together in the backend.
        """

        def __init__(self, *, workspace_id: str, run_id: str, provider: str, model: str) -> None:
            self._workspace_id = workspace_id
            self._run_id = run_id
            self._provider = provider
            self._model = model
            self._open: dict[Any, tuple[trace.Span, float]] = {}

        def _start(self, run_id: Any) -> None:
            span = tracer().start_span(
                f"chat {self._model}",
                attributes={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.system": self._provider,
                    "gen_ai.request.model": self._model,
                    "helix.kind": "deep",
                    "helix.run_id": self._run_id,
                    "helix.workspace_id": self._workspace_id,
                },
            )
            self._open[run_id] = (span, time.monotonic())

        def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs) -> None:
            self._start(run_id)

        def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs) -> None:
            self._start(run_id)

        def on_llm_end(self, response, *, run_id=None, **kwargs) -> None:
            entry = self._open.pop(run_id, None)
            if entry is None:
                return
            span, started = entry
            usage = _extract_usage(response)
            set_usage_attributes(span, usage)
            span.end()
            record_llm_call(
                workspace_id=self._workspace_id,
                kind="deep",
                provider=self._provider,
                model=self._model,
                usage=usage,
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        def on_llm_error(self, error, *, run_id=None, **kwargs) -> None:
            entry = self._open.pop(run_id, None)
            if entry is None:
                return
            span, _started = entry
            span.set_attribute("error.type", type(error).__name__)
            span.end()

    _handler_cls = LlmSpanHandler
    return _handler_cls


def make_llm_span_callback(*, workspace_id: str, run_id: str, provider: str, model: str):
    """A per-run LangChain callback handler tracing every LLM call it sees."""
    return _get_handler_cls()(
        workspace_id=workspace_id, run_id=run_id, provider=provider, model=model
    )
