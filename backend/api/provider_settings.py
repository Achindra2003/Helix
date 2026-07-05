"""Per-workspace LLM provider settings: the BYO-key seam.

The server's `.env` stops being the only place a provider can be configured.
Each workspace may carry its own provider choice, API key (encrypted at rest),
base URL, and model names; the server-wide settings remain the *fallback*, so
self-hosters configure nothing new and a hosted instance simply ships with no
fallback key. Resolution is one pure function (`resolve`) so it is trivially
unit-testable; the key never leaves the server in any API response.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .models import WorkspaceSettings

# Providers a workspace may select. "" means "inherit the server default".
# `openai_compatible` is one shape that covers OpenRouter, vLLM, LM Studio, a
# publicly reachable Ollama in OpenAI mode, and most future providers: a base
# URL serving POST {base_url}/chat/completions.
PROVIDER_CHOICES = ("", "groq", "openai_compatible", "ollama")

# Providers that cannot work without an API key.
_KEY_REQUIRED = {"groq"}


def _fernet() -> Fernet:
    """Encryption keyed off the server secret (the one secret that must already
    exist). Rotating `jwt_secret` therefore invalidates stored workspace keys —
    owners re-paste them; the failure mode is a clear "no key", never a leak."""
    digest = hashlib.sha256(f"helix-provider-keys:{settings.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_key(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_key(token: str) -> str:
    """"" on any failure: an undecryptable key behaves exactly like a missing
    key (the UI says "add a key"), never like a crash."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def mask_key(plain: str) -> str:
    """Display form: enough to recognise ("did I paste the right key?"),
    never enough to use."""
    if not plain:
        return ""
    if len(plain) <= 8:
        return "…" + plain[-2:]
    return f"{plain[:4]}…{plain[-4:]}"


@dataclass(frozen=True)
class ResolvedProvider:
    """The provider configuration one workspace's LLM calls actually use."""

    provider: str  # stub | groq | openai_compatible | ollama
    api_key: str
    base_url: str
    chat_model: str
    deep_model: str
    source: str  # "workspace" | "server"

    @property
    def missing_key(self) -> bool:
        return self.provider in _KEY_REQUIRED and not self.api_key

    @property
    def deep_groq_key(self) -> str:
        """Deep Reasoning runs on Groq (the engine builds a ChatGroq client).
        A workspace's own Groq key wins; any other provider choice falls back
        to the server-wide key so self-host setups keep working."""
        if self.provider == "groq" and self.api_key:
            return self.api_key
        return settings.groq_api_key

    @property
    def resolved_deep_model(self) -> str:
        return self.deep_model or settings.deep_reasoning_model


def _server_default() -> ResolvedProvider:
    provider = settings.llm_provider.lower()
    return ResolvedProvider(
        provider=provider,
        api_key=settings.groq_api_key if provider == "groq" else "",
        base_url=settings.ollama_base_url if provider == "ollama" else "",
        chat_model=settings.ollama_model if provider == "ollama" else settings.groq_model,
        deep_model=settings.deep_reasoning_model,
        source="server",
    )


def resolve(row: WorkspaceSettings | None) -> ResolvedProvider:
    """Workspace settings if present and set; otherwise the server default."""
    if row is None or not row.provider:
        return _server_default()
    provider = row.provider.lower()
    default_chat = {
        "groq": settings.groq_model,
        "ollama": settings.ollama_model,
    }.get(provider, "")
    return ResolvedProvider(
        provider=provider,
        api_key=decrypt_key(row.api_key_encrypted),
        base_url=(row.base_url or "").rstrip("/"),
        chat_model=row.chat_model or default_chat,
        deep_model=row.deep_model or "",
        source="workspace",
    )


def build_chat_provider(resolved: ResolvedProvider):
    """Construct the streaming chat provider for a resolved configuration.

    Mirrors `providers.get_provider()` but from explicit values instead of
    ambient settings — the multi-tenant path.
    """
    if resolved.provider == "groq":
        from .providers.groq import GroqProvider

        return GroqProvider(api_key=resolved.api_key, model=resolved.chat_model)
    if resolved.provider == "openai_compatible":
        from .providers.groq import GroqProvider

        return GroqProvider(
            api_key=resolved.api_key,
            model=resolved.chat_model,
            url=f"{resolved.base_url}/chat/completions",
            name="openai_compatible",
        )
    if resolved.provider == "ollama":
        from .providers.ollama import OllamaProvider

        return OllamaProvider(base_url=resolved.base_url or None, model=resolved.chat_model or None)

    from .providers.stub import StubProvider

    return StubProvider()
