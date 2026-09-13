"""Judge router (SPEC.md §5.3): tiers ``frontier`` (Claude), ``second_opinion``
(OpenAI), ``local`` (distilled judge on vLLM) and ``nli`` (DeBERTa).

Configuration is environment-driven so the same code runs in the API, the
worker and the CLI:

    LENS_JUDGE_FRONTIER_MODEL        default anthropic/claude-sonnet-5
    LENS_JUDGE_SECOND_OPINION_MODEL  default openai/gpt-4.1
    LENS_JUDGE_LOCAL_MODEL           default openai/lens-judge-small
    LENS_JUDGE_LOCAL_BASE_URL        default http://localhost:8001/v1
    LENS_JUDGE_EMBEDDING_MODEL       default openai/text-embedding-3-small
    LENS_JUDGE_CASSETTE              path to a cassette file: replay instead of calling LLMs
"""

from __future__ import annotations

import os
from pathlib import Path

from lens_core.judges.base import Judge
from lens_core.judges.cassette import CassetteJudge

TIERS: tuple[str, ...] = ("frontier", "second_opinion", "local", "nli")

DEFAULTS: dict[str, str] = {
    "frontier": "anthropic/claude-sonnet-5",
    "second_opinion": "openai/gpt-4.1",
    "local": "openai/lens-judge-small",
    "embedding": "openai/text-embedding-3-small",
    "local_base_url": "http://localhost:8001/v1",
}


class JudgeRouter:
    def __init__(self, judges: dict[str, Judge] | None = None) -> None:
        self._judges: dict[str, Judge] = dict(judges or {})

    def register(self, tier: str, judge: Judge) -> None:
        self._judges[tier] = judge

    def get(self, tier: str = "frontier") -> Judge:
        if tier in self._judges:
            return self._judges[tier]
        if tier == "nli" and "local" in self._judges:
            return self._judges["local"]
        raise KeyError(f"no judge registered for tier {tier!r}; have {sorted(self._judges)}")

    def has(self, tier: str) -> bool:
        return tier in self._judges

    @property
    def tiers(self) -> list[str]:
        return sorted(self._judges)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> JudgeRouter:
        e = env if env is not None else dict(os.environ)
        router = cls()
        cassette = e.get("LENS_JUDGE_CASSETTE")
        if cassette:
            judge = CassetteJudge(Path(cassette))
            for tier in TIERS:
                router.register(tier, judge)
            return router
        from lens_core.judges.litellm_judge import LiteLLMJudge

        embedding = e.get("LENS_JUDGE_EMBEDDING_MODEL", DEFAULTS["embedding"])
        router.register(
            "frontier",
            LiteLLMJudge(
                e.get("LENS_JUDGE_FRONTIER_MODEL", DEFAULTS["frontier"]),
                tier="frontier",
                embedding_model=embedding,
            ),
        )
        router.register(
            "second_opinion",
            LiteLLMJudge(
                e.get("LENS_JUDGE_SECOND_OPINION_MODEL", DEFAULTS["second_opinion"]),
                tier="second_opinion",
                embedding_model=embedding,
            ),
        )
        router.register(
            "local",
            LiteLLMJudge(
                e.get("LENS_JUDGE_LOCAL_MODEL", DEFAULTS["local"]),
                tier="local",
                api_base=e.get("LENS_JUDGE_LOCAL_BASE_URL", DEFAULTS["local_base_url"]),
                api_key=e.get("LENS_JUDGE_LOCAL_API_KEY", "local"),
            ),
        )
        return router
