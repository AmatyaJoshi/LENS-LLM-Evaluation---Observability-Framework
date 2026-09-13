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
    input: str
    expected_output: str | None = None
    contexts: list[str] | None = Field(default=None, sa_column=Column(JSON))
    metadata_: dict[str, Any] = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    split: str = "train"  # train | dev | test
    source_trace_id: str | None = Field(default=None, index=True)


class EvalRun(SQLModel, table=True):
    __tablename__ = "eval_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    dataset_id: UUID | None = Field(default=None, foreign_key="datasets.id", index=True)
    app: str = Field(index=True)
    git_sha: str | None = Field(default=None, index=True)
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
    judge_model: str | None = None
    judge_prompt_version: str | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    created_at: datetime = Field(default_factory=_now)


class HumanLabel(SQLModel, table=True):
    __tablename__ = "human_labels"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    trace_id: str | None = Field(default=None, index=True)
    example_id: UUID | None = Field(default=None, foreign_key="examples.id", index=True)
    metric: str = Field(index=True)
    value: float
    labeller: str
    notes: str | None = None
    created_at: datetime = Field(default_factory=_now)
