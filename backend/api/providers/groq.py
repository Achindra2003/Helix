import json
from typing import AsyncIterator

import httpx

from ..config import settings
from .base import Message

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    """Streaming inference against any OpenAI-compatible chat-completions API.

    Defaults to Groq on the server-wide key/model; a workspace's own settings
    construct it with explicit values instead (and, via `url`, can point it at
    any other OpenAI-compatible endpoint — OpenRouter, vLLM, LM Studio…).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        url: str = GROQ_URL,
        name: str = "groq",
    ):
        self.name = name
        self._api_key = settings.groq_api_key if api_key is None else api_key
        self._model = model or settings.groq_model
        self._url = url

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async for chunk in self.stream_messages([{"role": "user", "content": prompt}]):
            yield chunk

    async def stream_messages(self, messages: list[Message]) -> AsyncIterator[str]:
        """Send the role-structured context natively (OpenAI-compatible)."""
        if not self._api_key and self._url == GROQ_URL:
            # Groq itself always needs a key; a custom endpoint may not (vLLM etc.).
            raise RuntimeError("Groq provider selected but no API key is configured")

        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        body = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", self._url, headers=headers, json=body) as resp:
                if resp.status_code == 429:
                    # Rate limit: degrade to a clear, visible notice
                    # rather than a torn/empty stream.
                    yield "[Provider rate limit reached — please retry in a moment.]"
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
