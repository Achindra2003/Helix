from typing import AsyncIterator, Protocol

from ..config import settings

Message = dict[str, str]  # OpenAI/Groq shape: {"role": ..., "content": ...}


class LLMProvider(Protocol):
    """A streaming chat provider. Implementations yield response text in chunks.

    Two entry points, by design:
    - `stream(prompt)` — the original single-string path (week-0 `/chat/stream`).
    - `stream_messages(messages)` — role-structured multi-turn context, the shape
      the conversation engine uses so a thread's *shared, branchable context* is
      passed to the model as real `system`/`user`/`assistant` turns. Groq takes it
      natively (OpenAI-compatible); providers without a chat-messages API fall back
      to `render_messages_to_prompt`.
    """

    name: str

    def stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield the model's reply token-by-token (or chunk-by-chunk)."""
        ...

    def stream_messages(self, messages: list[Message]) -> AsyncIterator[str]:
        """Yield the reply for a role-structured chat context, chunk-by-chunk."""
        ...


def render_messages_to_prompt(messages: list[Message]) -> str:
    """Flatten role-structured messages into one prompt string.

    The fallback for providers without a native chat-messages API (e.g. Ollama):
    the system frame leads, each turn is rendered `role: content`, and a trailing
    `assistant:` cues the model to continue.
    """
    lines: list[str] = []
    for m in messages:
        role, content = m["role"], m["content"]
        lines.append(content if role == "system" else f"{role}: {content}")
    lines.append("assistant:")
    return "\n".join(lines)


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
