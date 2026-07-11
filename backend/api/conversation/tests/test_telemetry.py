"""Observability: GenAI spans + the usage ledger, driven through a real chat
turn. The suite stays hermetic — spans land in an in-memory exporter, never a
network; usage comes from the stub provider's deterministic fabrication.
"""
import time

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.testclient import TestClient

from api.main import app
from api.providers.pricing import estimate_cost_usd

# Installed at import, before any span starts: OTel's proxy tracer delegates to
# whatever provider is set globally, so every helix span in this test process
# lands here. (Without this, spans are no-ops — exactly the production default.)
_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)


def _span_names() -> list[str]:
    return [s.name for s in _exporter.get_finished_spans()]


def test_chat_turn_emits_genai_span_with_real_usage(make_workspace):
    _exporter.clear()
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t", "visibility": "shared"},
            headers=headers,
        ).json()
        sent = client.post(
            f"/conversations/{conv['branch_id']}/messages",
            json={"prompt": "trace me"},
            headers=headers,
        )
        assert sent.status_code == 200

    spans = _exporter.get_finished_spans()
    llm = [s for s in spans if s.attributes.get("gen_ai.operation.name") == "chat"]
    assert llm, f"no gen_ai chat span among {_span_names()}"
    span = llm[0]
    assert span.attributes["gen_ai.system"] == "stub"
    # The stub fabricates deterministic usage — the pipeline must carry it.
    assert span.attributes["gen_ai.usage.input_tokens"] >= 1
    assert span.attributes["gen_ai.usage.output_tokens"] >= 1


def test_chat_turn_lands_in_the_usage_ledger(make_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t", "visibility": "shared"},
            headers=headers,
        ).json()
        client.post(
            f"/conversations/{conv['branch_id']}/messages",
            json={"prompt": "bill me"},
            headers=headers,
        )
        # The ledger write is fire-and-forget on the app loop — give it a beat.
        calls = []
        for _ in range(40):
            usage = client.get(f"/api/workspaces/{wid}/usage", headers=headers).json()
            calls = usage.get("calls", [])
            if calls:
                break
            time.sleep(0.05)
        assert calls, "no llm_calls ledger row appeared"
        assert calls[0]["kind"] == "chat"
        assert calls[0]["provider"] == "stub"
        assert calls[0]["input_tokens"] >= 1
        assert calls[0]["output_tokens"] >= 1
        # The stub isn't in the price table: tokens reported, cost honestly None.
        assert calls[0]["cost_usd"] is None


def test_pricing_estimates_known_models_and_refuses_unknown():
    known = estimate_cost_usd("llama-3.3-70b-versatile", 1_000_000, 1_000_000)
    assert known is not None and abs(known - (0.59 + 0.79)) < 1e-9
    # Versioned/extended ids still match by prefix.
    assert estimate_cost_usd("llama-3.1-8b-instant-128k", 100, 100) is not None
    assert estimate_cost_usd("some-unknown-model", 100, 100) is None
    assert estimate_cost_usd("", 100, 100) is None
