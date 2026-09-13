"""initial evaluation records (SPEC.md §3.2)

Revision ID: 0001
Revises:
Create Date: 2026-09-14
"""
from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("split_strategy", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_datasets_name", "datasets", ["name"], unique=True)

    op.create_table(
        "examples",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("input", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expected_output", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("contexts", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("split", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_trace_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index("ix_examples_dataset_id", "examples", ["dataset_id"])
    op.create_index("ix_examples_source_trace_id", "examples", ["source_trace_id"])

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("app", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("git_sha", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_eval_runs_dataset_id", "eval_runs", ["dataset_id"])
    op.create_index("ix_eval_runs_app", "eval_runs", ["app"])
    op.create_index("ix_eval_runs_git_sha", "eval_runs", ["git_sha"])

    op.create_table(
        "scores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("eval_runs.id"), nullable=True),
        sa.Column("trace_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("example_id", sa.Uuid(), sa.ForeignKey("examples.id"), nullable=True),
        sa.Column("metric", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("metric_version", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("rationale", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("sub_scores", sa.JSON(), nullable=True),
        sa.Column("judge_model", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("judge_prompt_version", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("run_id", "trace_id", "example_id", "metric"):
        op.create_index(f"ix_scores_{col}", "scores", [col])

    op.create_table(
        "human_labels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("trace_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("example_id", sa.Uuid(), sa.ForeignKey("examples.id"), nullable=True),
        sa.Column("metric", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("labeller", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("trace_id", "example_id", "metric"):
        op.create_index(f"ix_human_labels_{col}", "human_labels", [col])


def downgrade() -> None:
    for table in ("human_labels", "scores", "eval_runs", "examples", "datasets"):
        op.drop_table(table)
