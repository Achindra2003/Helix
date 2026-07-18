"""Model pricing — turns the usage ledger's token counts into dollar estimates.

Prices are USD per **million** tokens, matching how providers publish them.
This table is a best-effort snapshot (Groq's public list pricing, mid-2026);
prices drift, so every figure this produces is labeled an *estimate* at the
API surface. An unknown model yields None — the UI then shows tokens only,
never a made-up dollar figure. Match is by prefix so versioned model ids
(`llama-3.3-70b-versatile-128k` etc.) still resolve.
"""
from __future__ import annotations

# model-id prefix -> (input $/1M tokens, output $/1M tokens)
PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "gemma2-9b-it": (0.20, 0.20),
    "llama-guard": (0.20, 0.20),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated USD cost of one (or an aggregate of) call(s); None if the
    model isn't in the table — honesty over invention."""
    if not model:
        return None
    for prefix, (in_price, out_price) in PRICES_PER_MILLION.items():
        if model.startswith(prefix):
            return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    return None
