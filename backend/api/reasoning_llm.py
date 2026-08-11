"""The LangChain chat client Deep Reasoning and agent runs call.

Both of those paths used to build a `ChatGroq` directly, which quietly made
Groq the only provider they could ever use: a workspace on Ollama or an
OpenAI-compatible endpoint had its deep runs sent to the *server's* Groq key,
and a purely self-hosted instance with no Groq account could not run the
product's flagship feature at all. The everyday chat path had been
provider-agnostic since the BYO-key seam landed; only these two had not caught
up.

**`ChatGroq` cannot be reused for this.** It accepts a `base_url`, which looks
like it would be enough, but the Groq SDK appends its own
`/openai/v1/chat/completions` to whatever it is given — point it at
`http://localhost:11434/v1` and the request goes to
`http://localhost:11434/v1/openai/v1/chat/completions`, which 404s. That was
measured, not assumed. So Groq keeps its own tested client and everything else
uses the generic OpenAI one.
"""
from __future__ import annotations

from typing import Any


def build_reasoning_llm(*, model: str, api_key: str, base_url: str = "", temperature: float = 0.7):
    """A LangChain chat model for `model` at `base_url`.

    `base_url=""` means Groq's own API (the historical path, unchanged).
    Anything else is an OpenAI-compatible endpoint.

    Imported lazily by callers: the LangChain stack is a heavy import that the
    everyday chat engine never needs.
    """
    if not base_url:
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, temperature=temperature, api_key=api_key or None)

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "base_url": base_url,
        # Local servers ignore the key but the client insists on one; a
        # placeholder keeps a keyless Ollama working instead of erroring here.
        "api_key": api_key or "not-needed",
    }
    return ChatOpenAI(**kwargs)


def make_reachability_probe():
    """Did this run ever actually reach a model?

    Every node in the vendored Ouroboros engine catches *all* exceptions from
    its LLM call and substitutes a canned line — "I cannot stop returning to
    this. Why does it grip me so?" and friends. For the standalone engine, which
    is meant to keep dreaming through a flaky connection, that is the right
    behaviour. Inside Helix it is not: a workspace pointed at a dead endpoint
    produced a complete, plausible-looking reasoning run, reported it as `done`,
    and showed convergence — reasoning the team never did, presented as
    reasoning the team did. Measured, not theorised: a 404 endpoint yielded 157
    steps and zero tokens.

    So the run is watched from outside the engine. If nothing ever succeeded and
    something failed, the run is an error and says why.
    """
    from langchain_core.callbacks import BaseCallbackHandler

    class Reachability(BaseCallbackHandler):
        def __init__(self) -> None:
            self.ok = 0
            self.errors = 0
            self.last_error = ""

        def on_llm_end(self, response, **kwargs) -> None:
            self.ok += 1

        def on_llm_error(self, error, **kwargs) -> None:
            self.errors += 1
            self.last_error = str(error)[:300]

        @property
        def never_reached_model(self) -> bool:
            """Deliberately requires a *seen* failure. A run that made no calls
            at all (killed before it started, say) is not misreported as a
            provider problem."""
            return self.ok == 0 and self.errors > 0

    return Reachability()
