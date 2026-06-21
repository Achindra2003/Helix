import asyncio
from typing import AsyncIterator


class StubProvider:
    """Zero-setup provider: echoes the prompt back word-by-word with a small
    delay, so the streaming pipeline is demoable with no API key or model."""

    name = "stub"

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        reply = f"(stub reply) You said: {prompt}"
        for word in reply.split(" "):
            await asyncio.sleep(0.05)
            yield word + " "
