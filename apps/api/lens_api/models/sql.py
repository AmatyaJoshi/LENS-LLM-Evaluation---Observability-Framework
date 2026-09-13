"""Relational models (SPEC.md §3.2) via SQLModel. Migrations: Alembic (apps/api/migrations/alembic).

``Score`` rows are immutable: re-judging inserts a new row (provenance).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class Dataset(SQLModel, table=True):
    __tablename__ = "datasets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
    split_strategy: str = "random"  # random | by_source_document | manual
    created_at: datetime = Field(default_factory=_now)


class Example(SQLModel, table=True):
    __tablename__ = "examples"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    dataset_id: UUID = Field(foreign_key="datasets.id", index=True)
    external_id: str | None = Field(default=None, index=True)
    input: str
    output: str | None = None  # recorded app output, when scoring without re-running
    expected_output: str | None = None
    contexts: list[str] | None = Field(default=None, sa_column=Column(JSON))
    expected_tools: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    metadata_: dict[str, Any] = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    split: str = "train"  # train | dev | test
    source_trace_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_now)


class EvalRun(SQLModel, table=True):
    __tablename__ = "eval_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    dataset_id: UUID | None = Field(default=None, foreign_key="datasets.id", index=True)
    app: str = Field(index=True)
    git_sha: str | None = Field(default=None, index=True)
    mode: str = "offline"  # offline | online | ci
    judge_tier: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class Score(SQLModel, table=True):
    __tablename__ = "scores"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID | None = Field(default=None, foreign_key="eval_runs.id", index=True)
    trace_id: str | None = Field(default=None, index=True)
    example_id: UUID | None = Field(default=None, foreign_key="examples.id", index=True)
    metric: str = Field(index=True)
    metric_version: str
    value: float
    rationale: str | None = None
    sub_scores: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    details: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    judge_model: str | None = Field(default=None, index=True)
    judge_tier: str | None = None
    judge_prompt_version: str | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    skipped: bool = False
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)


class HumanLabel(SQLModel, table=True):
    __tablename__ = "human_labels"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    trace_id: str | None = Field(default=None, index=True)
    example_id: UUID | None = Field(default=None, foreign_key="examples.id", index=True)
    metric: str = Field(index=True)
    value: float
    labeller: str = Field(index=True)
    notes: str | None = None
    created_at: datetime = Field(default_factory=_now)


class JudgeCalibration(SQLModel, table=True):
    __tablename__ = "judge_calibrations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    judge_model: str = Field(index=True)
    metric: str = Field(index=True)
    method: str  # temperature | isotonic
    params: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    n: int = 0
    brier_raw: float = 0.0
    brier_calibrated: float = 0.0
    created_at: datetime = Field(default_factory=_now)


class RedteamRun(SQLModel, table=True):
    __tablename__ = "redteam_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    app: str = Field(index=True)
    target: str
    git_sha: str | None = Field(default=None, index=True)
    defence: str | None = None  # free-text label of the defence configuration under test
    config_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    total_probes: int = 0
    successes: int = 0
    asr: float = 0.0
    detector_caught: int = 0
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class ProbeResult(SQLModel, table=True):
    __tablename__ = "probe_results"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="redteam_runs.id", index=True)
    probe_id: str = Field(index=True)
    parent_probe_id: str | None = None
    category: str = Field(index=True)
    tactic: str | None = None
    mutator: str | None = Field(default=None, index=True)
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    response: str | None = None
    success: bool = False
    success_reason: str | None = None
    detector_score: float | None = None
    detector_flagged: bool = False
    judge_rationale: str | None = None
    latency_ms: float | None = None
    trace_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_now)
