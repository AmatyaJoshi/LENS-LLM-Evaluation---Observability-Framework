"""Shared helpers and judge output schemas for the built-in metrics."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["supported", "contradicted", "unverifiable"]


class Claims(BaseModel):
    claims: list[str] = Field(default_factory=list)


class ClaimVerdict(BaseModel):
    claim: str
    verdict: Verdict
    evidence: str | None = None


class Verdicts(BaseModel):
    verdicts: list[ClaimVerdict] = Field(default_factory=list)


class Questions(BaseModel):
    questions: list[str] = Field(default_factory=list)


class RubricScore(BaseModel):
    score: int = Field(ge=1, le=5)
    rationale: str = ""
    evidence_spans: list[str] = Field(default_factory=list)


class YesNo(BaseModel):
    answer: Literal["yes", "no"]
    rationale: str = ""


class YesNoList(BaseModel):
    answers: list[YesNo] = Field(default_factory=list)


class PairwiseChoice(BaseModel):
    winner: Literal["A", "B", "tie"]
    rationale: str = ""


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 2]


def numbered(items: Sequence[str]) -> str:
    return "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(items))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rubric_to_unit(score: int) -> float:
    """Map a 1-5 rubric score to [0, 1]."""
    return (max(1, min(5, score)) - 1) / 4
