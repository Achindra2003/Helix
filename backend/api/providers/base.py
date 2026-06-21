from typing import AsyncIterator, Protocol

from ..config import settings


class LLMProvider(Protocol):
    """A streaming chat provider. Implementations yield response text in chunks."""

    name: str

    def stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield the model's reply token-by-token (or chunk-by-chunk)."""
        ...


def get_provider() -> LLMProvider:
    """Select the provider from config. Defaults to the zero-setup stub."""
    provider = settings.llm_provider.lower()

    if provider == "groq":
        from .groq import GroqProvider

        return GroqProvider()
    if provider == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider()

    from .stub import StubProvider

    return StubProvider()
