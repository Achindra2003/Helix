import asyncio
from typing import AsyncIterator

from .base import Message


class StubProvider:
    """Zero-setup provider: echoes the prompt back word-by-word with a small
    delay, so the streaming pipeline is demoable with no API key or model."""

    name = "stub"

    async def _echo(self, text: str) -> AsyncIterator[str]:
        reply = f"(stub reply) You said: {text}"
        for word in reply.split(" "):
            await asyncio.sleep(0.05)
            yield word + " "

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async for chunk in self._echo(prompt):
            yield chunk

    async def stream_messages(self, messages: list[Message]) -> AsyncIterator[str]:
        """Echo the most recent user turn — enough to prove context flows through."""
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        async for chunk in self._echo(last_user):
            yield chunk
