"""Per-workspace provider settings: encryption, resolution, RBAC, and the
no-key guard on the chat route.

The raw key must never appear in any API response; a workspace with a
key-requiring provider and no key must fail loud-and-early (503), not stream
torn output.
"""
import pytest
from starlette.testclient import TestClient

import api.conversation.router as conv_router_mod
import api.routers.workspaces as workspaces_mod
from api.conversation.store import InMemoryStore
from api.main import app
from api.models import WorkspaceSettings
from api.provider_settings import (
    ResolvedProvider,
    decrypt_key,
    encrypt_key,
    mask_key,
    resolve,
)
from api.providers.stub import StubProvider


# --- unit: crypto + resolution ---------------------------------------------------

def test_encrypt_roundtrip_and_garbage_decrypts_to_empty():
    token = encrypt_key("gsk_super_secret_1234")
    assert token != "gsk_super_secret_1234"
    assert decrypt_key(token) == "gsk_super_secret_1234"
    assert decrypt_key("not-a-fernet-token") == ""  # missing key, never a crash
    assert encrypt_key("") == "" and decrypt_key("") == ""


def test_mask_key_shows_recognition_not_material():
    assert mask_key("gsk_abcdefghij5678") == "gsk_…5678"
    assert mask_key("short") == "…rt"
    assert mask_key("") == ""


def test_resolve_falls_back_to_server_settings():
    resolved = resolve(None)
    assert resolved.source == "server"
    assert resolved.provider == "stub"  # hermetic env
    empty_row = WorkspaceSettings(workspace_id="w1", provider="")
    assert resolve(empty_row).source == "server"


def test_resolve_workspace_row_wins_and_flags_missing_key():
    row = WorkspaceSettings(
        workspace_id="w1",
        provider="groq",
        api_key_encrypted=encrypt_key("gsk_live_key"),
        chat_model="",
        deep_model="my-deep-model",
    )
    resolved = resolve(row)
    assert resolved.source == "workspace"
    assert resolved.api_key == "gsk_live_key"
    assert resolved.chat_model  # falls back to the default groq chat model
    assert resolved.resolved_deep_model == "my-deep-model"
    assert resolved.deep_llm.api_key == "gsk_live_key"  # workspace groq key wins
    assert resolved.deep_llm.base_url == ""  # Groq's own API, not a custom host
    assert not resolved.missing_key

    keyless = resolve(WorkspaceSettings(workspace_id="w1", provider="groq"))
    assert keyless.missing_key  # groq without a key is unusable, and says so


def test_deep_runs_follow_a_local_ollama_instead_of_reaching_for_groq(monkeypatch):
    """The defect this replaced: a workspace on Ollama sent its deep runs to
    the *server's* Groq key, so a purely self-hosted instance with no Groq
    account could not use Deep Reasoning at all."""
    import api.provider_settings as ps

    monkeypatch.setattr(ps.settings, "groq_api_key", "server-groq-key")
    row = WorkspaceSettings(
        workspace_id="w1", provider="ollama",
        base_url="http://localhost:11434", chat_model="llama3.2",
    )
    deep = resolve(row).deep_llm

    assert deep.base_url == "http://localhost:11434/v1"  # the OpenAI-compatible surface
    assert deep.api_key == "ollama"  # a placeholder: local Ollama ignores it
    assert deep.api_key != "server-groq-key"  # and never borrows the server's
    # The Groq-shaped default model name would 404 on Ollama, so the model the
    # workspace already chats with is used instead.
    assert deep.model == "llama3.2"


def test_deep_runs_follow_an_openai_compatible_endpoint(monkeypatch):
    import api.provider_settings as ps

    monkeypatch.setattr(ps.settings, "groq_api_key", "server-groq-key")
    row = WorkspaceSettings(
        workspace_id="w1", provider="openai_compatible",
        base_url="https://openrouter.ai/api/v1", chat_model="some/model",
        api_key_encrypted=encrypt_key("sk-router"),
    )
    deep = resolve(row).deep_llm

    assert (deep.api_key, deep.base_url, deep.model) == (
        "sk-router", "https://openrouter.ai/api/v1", "some/model",
    )


def test_an_explicit_deep_model_wins_on_every_provider():
    row = WorkspaceSettings(
        workspace_id="w1", provider="ollama",
        base_url="http://localhost:11434", chat_model="llama3.2",
        deep_model="deepseek-r1:14b",
    )
    assert resolve(row).deep_llm.model == "deepseek-r1:14b"


def test_a_server_default_workspace_still_uses_the_server_groq_key(monkeypatch):
    """Self-host setups that configured one server-wide Groq key and never
    touched per-workspace settings must keep working unchanged."""
    import api.provider_settings as ps

    monkeypatch.setattr(ps.settings, "groq_api_key", "server-groq-key")
    monkeypatch.setattr(ps.settings, "llm_provider", "groq")
    assert resolve(None).deep_llm.api_key == "server-groq-key"


# --- HTTP: RBAC + write-only key -------------------------------------------------

def test_settings_owner_writes_member_reads_key_never_leaves(make_workspace, join_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        member_headers, _mid = join_workspace(client, headers, wid)

        put = client.put(
            f"/api/workspaces/{wid}/settings/provider",
            json={"provider": "groq", "api_key": "gsk_brand_new_key_9876"},
            headers=headers,
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["api_key_masked"] == "gsk_…9876"
        assert "gsk_brand_new_key_9876" not in put.text  # raw key never echoes

        # A collaborator can read status (composer needs it) but no key material.
        got = client.get(
            f"/api/workspaces/{wid}/settings/provider", headers=member_headers
        )
        assert got.status_code == 200
        member_view = got.json()
        assert member_view["effective_provider"] == "groq"
        assert member_view["configured"] is True
        assert "api_key_masked" not in member_view and "base_url" not in member_view

        # A collaborator cannot write.
        deny = client.put(
            f"/api/workspaces/{wid}/settings/provider",
            json={"provider": ""},
            headers=member_headers,
        )
        assert deny.status_code == 403


def test_settings_key_keep_and_clear_semantics(make_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        url = f"/api/workspaces/{wid}/settings/provider"
        client.put(url, json={"provider": "groq", "api_key": "gsk_original_key_1111"}, headers=headers)

        # api_key omitted (None) -> stored key is kept.
        kept = client.put(url, json={"provider": "groq", "chat_model": "llama-x"}, headers=headers)
        assert kept.json()["api_key_masked"] == "gsk_…1111"
        assert kept.json()["chat_model"] == "llama-x"

        # api_key "" -> cleared; groq without a key reports unconfigured.
        cleared = client.put(url, json={"provider": "groq", "api_key": ""}, headers=headers)
        assert cleared.json()["api_key_masked"] == ""
        assert cleared.json()["configured"] is False


def test_settings_validation(make_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        url = f"/api/workspaces/{wid}/settings/provider"
        assert client.put(url, json={"provider": "made-up"}, headers=headers).status_code == 400
        assert (
            client.put(url, json={"provider": "openai_compatible"}, headers=headers).status_code
            == 400  # needs a base_url
        )
        ok = client.put(
            url,
            json={"provider": "openai_compatible", "base_url": "https://api.example.dev/v1/"},
            headers=headers,
        )
        assert ok.status_code == 200
        assert ok.json()["base_url"] == "https://api.example.dev/v1"  # trailing / stripped


def test_test_connection_reports_rather_than_raises(make_workspace, monkeypatch):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        url = f"/api/workspaces/{wid}/settings/provider"

        # groq with no key: a clear negative result, not a 500.
        client.put(url, json={"provider": "groq", "api_key": ""}, headers=headers)
        res = client.post(f"{url}/test", headers=headers).json()
        assert res["ok"] is False and "key" in res["detail"].lower()

        # With the provider swapped for the stub, the round-trip succeeds.
        client.put(url, json={"provider": "groq", "api_key": "gsk_k"}, headers=headers)
        monkeypatch.setattr(
            workspaces_mod, "build_chat_provider", lambda _r, **_kw: StubProvider()
        )
        res = client.post(f"{url}/test", headers=headers).json()
        assert res["ok"] is True, res


# --- HTTP: the chat route honours workspace settings ------------------------------

@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    monkeypatch.setattr(conv_router_mod, "_store", InMemoryStore())


def test_send_fails_503_when_workspace_provider_has_no_key(make_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        client.put(
            f"/api/workspaces/{wid}/settings/provider",
            json={"provider": "groq", "api_key": ""},
            headers=headers,
        )
        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t"},
            headers=headers,
        ).json()
        resp = client.post(
            f"/conversations/{conv['branch_id']}/messages",
            json={"prompt": "hi"},
            headers=headers,
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "provider_unconfigured"


def test_send_streams_when_workspace_inherits_server_default(make_workspace):
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        # No settings row at all -> server default (stub) -> streaming works.
        conv = client.post(
            "/conversations",
            json={"workspace_id": wid, "title": "t"},
            headers=headers,
        ).json()
        resp = client.post(
            f"/conversations/{conv['branch_id']}/messages",
            json={"prompt": "hello world"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "stub reply" in resp.text


def test_chat_provider_construction_uses_workspace_values():
    # The bare provider carries the resolved values verbatim…
    from api.provider_settings import build_chat_provider

    groq = build_chat_provider(
        ResolvedProvider(
            provider="groq", api_key="k", base_url="", chat_model="m",
            deep_model="", source="workspace",
        ),
        resilient=False,
    )
    assert groq.name == "groq" and groq._model == "m" and groq._api_key == "k"

    compat = build_chat_provider(
        ResolvedProvider(
            provider="openai_compatible", api_key="", base_url="http://vllm.local/v1",
            chat_model="qwen", deep_model="", source="workspace",
        ),
        resilient=False,
    )
    assert compat.name == "openai_compatible"
    assert compat._url == "http://vllm.local/v1/chat/completions"

    stub = build_chat_provider(
        ResolvedProvider(
            provider="stub", api_key="", base_url="", chat_model="",
            deep_model="", source="server",
        ),
        resilient=False,
    )
    assert stub.name == "stub"


def test_chat_provider_defaults_to_resilient_wrapper():
    # …while the default path wraps it in retry/breaker/fallback, reporting the
    # primary's name so it stays a drop-in provider.
    from api.provider_settings import build_chat_provider
    from api.providers.resilient import ResilientProvider

    wrapped = build_chat_provider(
        ResolvedProvider(
            provider="groq", api_key="k", base_url="", chat_model="m",
            deep_model="", source="workspace",
        )
    )
    assert isinstance(wrapped, ResilientProvider)
    assert wrapped.name == "groq"


def test_a_bad_key_is_tested_before_it_is_stored(make_workspace, monkeypatch):
    """It used to save first and then test, so a typo'd key became the
    workspace's live configuration and every message failed until someone
    corrected it. The panel could only report the breakage it had caused."""
    import api.routers.workspaces as ws

    class Dead:
        name = "groq"

        async def stream_messages(self, messages):
            raise RuntimeError("Invalid API Key")
            yield ""  # pragma: no cover - never reached

    monkeypatch.setattr(ws, "build_chat_provider", lambda resolved, resilient=True: Dead())

    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        r = client.post(f"/api/workspaces/{wid}/settings/provider/test", headers=headers,
                        json={"provider": "groq", "api_key": "gsk_typo",
                              "base_url": "", "chat_model": "m", "deep_model": ""})
        assert r.status_code == 200
        assert r.json()["ok"] is False

        # The candidate was never persisted: the workspace is untouched.
        after = client.get(f"/api/workspaces/{wid}/settings/provider", headers=headers).json()
        assert after["provider"] == ""
        assert after["api_key_masked"] == ""


def test_testing_without_a_key_falls_back_to_the_stored_one(make_workspace, monkeypatch):
    """Changing only the model must not require re-pasting a key the owner
    cannot read back."""
    import api.routers.workspaces as ws

    seen = {}

    class Echo:
        name = "groq"

        async def stream_messages(self, messages):
            yield "ok"

    def capture(resolved, resilient=True):
        seen["api_key"] = resolved.api_key
        seen["chat_model"] = resolved.chat_model
        return Echo()

    monkeypatch.setattr(ws, "build_chat_provider", capture)

    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        client.put(f"/api/workspaces/{wid}/settings/provider", headers=headers,
                   json={"provider": "groq", "api_key": "gsk_stored",
                         "base_url": "", "chat_model": "old", "deep_model": ""})

        r = client.post(f"/api/workspaces/{wid}/settings/provider/test", headers=headers,
                        json={"provider": "groq", "base_url": "",
                              "chat_model": "new-model", "deep_model": ""})
        assert r.json()["ok"] is True
        assert seen["api_key"] == "gsk_stored"  # the stored key, not blank
        assert seen["chat_model"] == "new-model"  # but the candidate's model


def test_testing_with_no_body_still_tests_what_is_stored(make_workspace, monkeypatch):
    """The old no-body call is still valid — nothing that used it breaks."""
    import api.routers.workspaces as ws

    class Echo:
        name = "groq"

        async def stream_messages(self, messages):
            yield "ok"

    monkeypatch.setattr(ws, "build_chat_provider", lambda resolved, resilient=True: Echo())
    with TestClient(app) as client:
        headers, _uid, wid = make_workspace(client)
        client.put(f"/api/workspaces/{wid}/settings/provider", headers=headers,
                   json={"provider": "groq", "api_key": "gsk_stored",
                         "base_url": "", "chat_model": "m", "deep_model": ""})
        assert client.post(f"/api/workspaces/{wid}/settings/provider/test",
                           headers=headers).json()["ok"] is True
