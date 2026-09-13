"""LiteLLM-backed judge: one class for Anthropic (frontier), OpenAI (second opinion)
and any OpenAI-compatible local server such as vLLM (``local`` tier).

``litellm`` is imported lazily so lens-core stays importable without it.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from lens_core.judges.base import Judge, JudgeError, JudgeResponse


class LiteLLMJudge(Judge):
    name = "litellm"

    def __init__(
        self,
        model: str,
        *,
        tier: str = "frontier",
        api_base: str | None = None,
        api_key: str | None = None,
        embedding_model: str | None = None,
        timeout: float = 60.0,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.tier = tier
        self.api_base = api_base
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.timeout = timeout
        self.extra = extra or {}
        self.name = f"{tier}:{model}"

    def _kwargs(self) -> dict[str, Any]:
        kw: dict[str, Any] = {"timeout": self.timeout, **self.extra}
        if self.api_base:
            kw["api_base"] = self.api_base
        if self.api_key:
            kw["api_key"] = self.api_key
        return kw

    async def _complete(
        self, system: str, user: str, *, temperature: float, max_tokens: int
    ) -> JudgeResponse:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover
            raise JudgeError("litellm is not installed; install lens-core[judges]") from exc
        t0 = time.perf_counter()
        try:
            resp = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=temperature,
                max_tokens=max_tokens,
                **self._kwargs(),
            )
        except Exception as exc:  # noqa: BLE001
            raise JudgeError(f"{self.name}: {type(exc).__name__}: {exc}") from exc
        latency = (time.perf_counter() - t0) * 1000
        choice = resp.choices[0]
        text = choice.message.content or ""
        usage = getattr(resp, "usage", None)
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        try:
            cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
        except Exception:  # noqa: BLE001 - unknown local models have no price
            cost = 0.0
        return JudgeResponse(
            text=text,
            model=str(getattr(resp, "model", self.model) or self.model),
            prompt_name="",
            prompt_version="",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            latency_ms=latency,
        )

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.embedding_model:
            return None
        try:
            import litellm
        except ImportError:  # pragma: no cover
            return None
        try:
            resp = await litellm.aembedding(
                model=self.embedding_model, input=texts, **self._kwargs()
            )
        except Exception as exc:  # noqa: BLE001
            raise JudgeError(f"embedding failed: {exc}") from exc
        with contextlib.suppress(Exception):
            self.stats.cost_usd += float(litellm.completion_cost(completion_response=resp) or 0.0)
        data = sorted(resp.data, key=lambda d: d["index"])
        return [list(map(float, d["embedding"])) for d in data]
