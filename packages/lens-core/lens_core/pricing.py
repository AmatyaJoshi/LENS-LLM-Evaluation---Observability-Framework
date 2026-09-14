"""LLM price table for cost accounting (SPEC.md §5, §8 cost columns).

Prices are USD per 1M tokens, (input, output). Model names are matched by longest
substring, so provider-prefixed ids (``openrouter/anthropic/claude-sonnet-5``,
``anthropic/claude-3.5-sonnet``, ``gpt-4o-mini-2024-07-18``) all resolve. Unknown
models return ``None`` (shown as "–" in the UI, never a fabricated number).

Update this table as prices change; it is the single source of cost truth.
"""

from __future__ import annotations

# (input $/1M, output $/1M). Keep keys lowercase; matching is case-insensitive substring.
PRICES: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    # Anthropic (Claude)
    "claude-3.5-haiku": (0.80, 4.00),
    "claude-3-haiku": (0.25, 1.25),
    "claude-3.5-sonnet": (3.00, 15.00),
    "claude-3.7-sonnet": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-opus-5": (15.00, 75.00),
    "claude-fable-5": (3.00, 15.00),
    # Google
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    # Meta / open models (typical hosted price)
    "llama-3.3-70b": (0.59, 0.79),
    "llama-3.1-8b": (0.05, 0.08),
    "qwen2.5-3b": (0.02, 0.04),
    # Lens local distilled judge served on vLLM (compute-only estimate)
    "lens-judge-small": (0.02, 0.04),
}

# Longest keys first so "claude-3.5-sonnet" wins over a hypothetical "claude".
_KEYS = sorted(PRICES, key=len, reverse=True)


def price_for(model: str) -> tuple[float, float] | None:
    """Return (input, output) $/1M for a model id, matched by substring, else None."""
    if not model:
        return None
    m = model.lower()
    for key in _KEYS:
        if key in m:
            return PRICES[key]
    return None


def cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """USD cost of a call, or None when the model's price is unknown."""
    p = price_for(model)
    if p is None:
        return None
    return round((tokens_in * p[0] + tokens_out * p[1]) / 1_000_000, 8)


def is_priced(model: str) -> bool:
    return price_for(model) is not None
