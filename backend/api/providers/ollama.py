import json
from typing import AsyncIterator

import httpx

from ..config import settings
from .base import Message, render_messages_to_prompt


class OllamaProvider:
    """Local inference via the Ollama HTTP API (streaming).

    Defaults to the server-wide base URL/model; per-workspace settings pass
    explicit values.
    """

    name = "ollama"

    def __init__(self, *, base_url: str | None = None, model: str | None = None):
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self.last_usage: dict | None = None

    async def stream_messages(self, messages: list[Message]) -> AsyncIterator[str]:
        """No native chat-messages call here — flatten to one prompt and stream."""
        async for chunk in self.stream(render_messages_to_prompt(messages)):
            yield chunk

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        url = f"{self._base_url}/api/generate"
        body = {"model": self._model, "prompt": prompt, "stream": True}

        self.last_usage = None
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("response"):
                        yield chunk["response"]
                    if chunk.get("done"):
                        # Ollama reports real counts on the terminal frame.
                        self.last_usage = {
                            "input_tokens": chunk.get("prompt_eval_count", 0),
                            "output_tokens": chunk.get("eval_count", 0),
                        }
                        break
