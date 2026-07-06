"""Capability registry: known models resolve, unknown models degrade safely."""
from api.providers.capabilities import capabilities


def test_known_model_reports_real_capabilities():
    caps = capabilities("llama-3.3-70b-versatile")
    assert caps.json_mode is True
    assert caps.tools is True
    assert caps.context_tokens >= 100_000


def test_unknown_model_falls_back_to_conservative_default():
    caps = capabilities("some-brand-new-model-2027")
    # Conservative: features gated off, modest window — never crashes or assumes.
    assert caps.json_mode is False
    assert caps.tools is False
    assert caps.context_tokens == 8_192


def test_none_or_empty_is_the_default():
    assert capabilities(None).json_mode is False
    assert capabilities("").tools is False


def test_match_is_case_insensitive_substring():
    # A fully-qualified name still matches on the family substring.
    assert capabilities("groq/LLaMA-3.1-8B-instant").context_tokens >= 100_000
