"""evaluation runs, scores provenance, judge calibrations, red-team runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14
"""
from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

S = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.add_column("examples", sa.Column("external_id", S(), nullable=True))
    op.add_column("examples", sa.Column("output", S(), nullable=True))
    op.add_column("examples", sa.Column("expected_tools", sa.JSON(), nullable=True))
    op.add_column("examples", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_examples_external_id", "examples", ["external_id"])

    op.add_column("eval_runs", sa.Column("mode", S(), nullable=False, server_default="offline"))
    op.add_column("eval_runs", sa.Column("judge_tier", S(), nullable=True))

    op.add_column("scores", sa.Column("details", sa.JSON(), nullable=True))
    op.add_column("scores", sa.Column("judge_tier", S(), nullable=True))
    op.add_column("scores", sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("scores", sa.Column("error", S(), nullable=True))
    op.create_index("ix_scores_judge_model", "scores", ["judge_model"])

    op.create_index("ix_human_labels_labeller", "human_labels", ["labeller"])

    op.create_table(
        "judge_calibrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("judge_model", S(), nullable=False),
        sa.Column("metric", S(), nullable=False),
        sa.Column("method", S(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("brier_raw", sa.Float(), nullable=False),
        sa.Column("brier_calibrated", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_judge_calibrations_judge_model", "judge_calibrations", ["judge_model"])
    op.create_index("ix_judge_calibrations_metric", "judge_calibrations", ["metric"])

    op.create_table(
        "redteam_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("app", S(), nullable=False),
        sa.Column("target", S(), nullable=False),
        sa.Column("git_sha", S(), nullable=True),
        sa.Column("defence", S(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("total_probes", sa.Integer(), nullable=False),
        sa.Column("successes", sa.Integer(), nullable=False),
        sa.Column("asr", sa.Float(), nullable=False),
        sa.Column("detector_caught", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_redteam_runs_app", "redteam_runs", ["app"])
    op.create_index("ix_redteam_runs_git_sha", "redteam_runs", ["git_sha"])

    op.create_table(
        "probe_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("redteam_runs.id"), nullable=False),
        sa.Column("probe_id", S(), nullable=False),
        sa.Column("parent_probe_id", S(), nullable=True),
        sa.Column("category", S(), nullable=False),
        sa.Column("tactic", S(), nullable=True),
        sa.Column("mutator", S(), nullable=True),
        sa.Column("messages", sa.JSON(), nullable=True),
        sa.Column("response", S(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("success_reason", S(), nullable=True),
        sa.Column("detector_score", sa.Float(), nullable=True),
        sa.Column("detector_flagged", sa.Boolean(), nullable=False),
        sa.Column("judge_rationale", S(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("trace_id", S(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("run_id", "probe_id", "category", "mutator", "trace_id"):
        op.create_index(f"ix_probe_results_{col}", "probe_results", [col])


def downgrade() -> None:
    op.drop_table("probe_results")
    op.drop_table("redteam_runs")
    op.drop_table("judge_calibrations")
    op.drop_index("ix_human_labels_labeller", "human_labels")
    op.drop_index("ix_scores_judge_model", "scores")
    for col in ("details", "judge_tier", "skipped", "error"):
        op.drop_column("scores", col)
    op.drop_column("eval_runs", "judge_tier")
    op.drop_column("eval_runs", "mode")
    op.drop_index("ix_examples_external_id", "examples")
    for col in ("created_at", "expected_tools", "output", "external_id"):
        op.drop_column("examples", col)
