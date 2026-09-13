"""Judge abstraction (SPEC.md §5.3).

A ``Judge`` turns a versioned prompt into a validated JSON object (or free text),
tracks cost and latency, and optionally embeds text. Concrete judges:
``LiteLLMJudge`` (frontier / second-opinion / local vLLM), ``CassetteJudge``
(recorded responses for tests) and ``NLIJudge`` (local DeBERTa, phase 7).
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError

from lens_core.judges.prompts import Prompt

T = TypeVar("T", bound=BaseModel)


class JudgeResponse(BaseModel):
    text: str
    model: str
    prompt_name: str
    prompt_version: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False


class JudgeError(RuntimeError):
    pass


class JudgeStats(BaseModel):
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms_total: float = 0.0
    cache_hits: int = 0
    latencies_ms: list[float] = Field(default_factory=list)

    def record(self, r: JudgeResponse) -> None:
        self.calls += 1
        self.tokens_in += r.tokens_in
        self.tokens_out += r.tokens_out
        self.cost_usd += r.cost_usd
        self.latency_ms_total += r.latency_ms
        self.latencies_ms.append(r.latency_ms)
        if r.cached:
            self.cache_hits += 1

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a judge reply (tolerates code fences and prose)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass
    m = _JSON_BLOCK.search(cleaned)
    if not m:
        raise JudgeError(f"no JSON object in judge reply: {text[:200]!r}")
    parsed = json.loads(m.group(0))
    if not isinstance(parsed, dict):
        raise JudgeError("judge reply JSON is not an object")
    return parsed


class Judge(ABC):
    """Base class with prompt rendering, JSON validation with one retry, and stats."""

    name: str = "judge"
    model: str = "unknown"
    tier: str = "frontier"

    def __init__(self) -> None:
        self.stats = JudgeStats()

    @property
    def cost_usd(self) -> float:
        return self.stats.cost_usd

    @abstractmethod
    async def _complete(
        self, system: str, user: str, *, temperature: float, max_tokens: int
    ) -> JudgeResponse:
        """Raw completion; implementations fill model/tokens/cost/latency."""

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Optional embeddings; ``None`` means unsupported (metrics fall back to a rubric)."""
        return None

    async def complete(
        self,
        prompt: Prompt,
        variables: dict[str, Any],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> JudgeResponse:
        system, user = prompt.render(variables)
        resp = await self._complete(system, user, temperature=temperature, max_tokens=max_tokens)
        resp.prompt_name = prompt.name
        resp.prompt_version = prompt.version
        self.stats.record(resp)
        return resp

    async def judge(
        self,
        prompt: Prompt,
        variables: dict[str, Any],
        schema: type[T],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> tuple[T, JudgeResponse]:
        """Complete and validate against ``schema``; retries once asking for strict JSON."""
        resp = await self.complete(
            prompt, variables, temperature=temperature, max_tokens=max_tokens
        )
        try:
            return schema.model_validate(extract_json(resp.text)), resp
        except (JudgeError, ValidationError, ValueError) as first:
            retry_vars = dict(variables)
            retry_vars["__retry_hint"] = (
                "Your previous reply was not valid JSON matching the schema. "
                "Reply with a single JSON object only."
            )
            resp2 = await self.complete(
                prompt, retry_vars, temperature=temperature, max_tokens=max_tokens
            )
            try:
                return schema.model_validate(extract_json(resp2.text)), resp2
            except (JudgeError, ValidationError, ValueError) as second:
                raise JudgeError(
                    f"judge output invalid after retry: {second} (first: {first})"
                ) from second
