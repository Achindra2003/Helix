import asyncio
from typing import AsyncIterator

from .base import Message


class StubProvider:
    """Zero-setup provider: echoes the prompt back word-by-word with a small
    delay, so the streaming pipeline is demoable with no API key or model."""

    name = "stub"

    def __init__(self) -> None:
        self.last_usage: dict | None = None

    async def _echo(self, text: str, input_words: int) -> AsyncIterator[str]:
        reply = f"(stub reply) You said: {text}"
        words = reply.split(" ")
        for word in words:
            await asyncio.sleep(0.05)
            yield word + " "
        # Fabricated but deterministic usage, so the accounting pipeline is
        # exercised hermetically (a word ≈ a token is fine for a stub).
        self.last_usage = {"input_tokens": max(1, input_words), "output_tokens": len(words)}

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async for chunk in self._echo(prompt, len(prompt.split())):
            yield chunk

    async def stream_messages(self, messages: list[Message]) -> AsyncIterator[str]:
        """Echo the most recent user turn — enough to prove context flows through."""
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        input_words = sum(len(m["content"].split()) for m in messages)
        async for chunk in self._echo(last_user, input_words):
            yield chunk
