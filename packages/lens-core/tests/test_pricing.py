from lens_core import pricing


def test_known_models_priced_by_substring() -> None:
    assert pricing.cost("gpt-4o-mini", 1_000_000, 0) == 0.15
    assert pricing.cost("openrouter/anthropic/claude-sonnet-5", 0, 1_000_000) == 15.0
    assert pricing.cost("gpt-4o-mini-2024-07-18", 1000, 1000) == round(
        (1000 * 0.15 + 1000 * 0.60) / 1e6, 8
    )
    assert pricing.is_priced("anthropic/claude-3.5-sonnet")


def test_unknown_model_returns_none() -> None:
    assert pricing.cost("some-unknown-model", 100, 100) is None
    assert pricing.price_for("") is None
    assert not pricing.is_priced("mystery")


def test_longest_match_wins() -> None:
    # claude-3.5-haiku must not be swallowed by claude-3-haiku or a generic key
    assert pricing.price_for("claude-3.5-haiku") == (0.80, 4.00)
