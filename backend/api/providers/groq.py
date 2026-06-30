import json
from typing import AsyncIterator

import httpx

from ..config import settings
from .base import Message

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    """Hosted inference via Groq's OpenAI-compatible streaming API."""

    name = "groq"

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async for chunk in self.stream_messages([{"role": "user", "content": prompt}]):
            yield chunk

    async def stream_messages(self, messages: list[Message]) -> AsyncIterator[str]:
        """Send the role-structured context to Groq natively (OpenAI-compatible)."""
        if not settings.groq_api_key:
            raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is empty")

        headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
        body = {
            "model": settings.groq_model,
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", GROQ_URL, headers=headers, json=body) as resp:
                if resp.status_code == 429:
                    # Free-tier rate limit: degrade to a clear, visible notice
                    # rather than a torn/empty stream.
                    yield "[Groq free-tier rate limit reached — please retry in a moment.]"
                    return
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :]
                    if data.strip() == "[DONE]":
                        break
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
