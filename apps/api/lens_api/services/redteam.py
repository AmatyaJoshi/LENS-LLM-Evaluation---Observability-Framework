"""Red-team service: launch a run against a target, persist results, aggregate ASR
(SPEC.md §6.4). Used by the API router, the CLI import endpoint and the Celery worker."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine
from sqlmodel import Session, select

from lens_api.db import engine_for
from lens_api.models.sql import ProbeResult, RedteamRun
from lens_api.settings import get_settings
from lens_core.redteam import RedteamRunner, RunReport, load_probes
from lens_core.redteam.runner import ProbeOutcome
from lens_core.redteam.targets import HttpTarget

log = logging.getLogger("lens.redteam")


def _outcome_row(run_id: UUID, o: ProbeOutcome) -> ProbeResult:
    return ProbeResult(
        run_id=run_id,
        probe_id=o.probe_id,
        parent_probe_id=o.parent_probe_id,
        category=o.category,
        tactic=o.tactic,
        mutator=o.mutator,
        messages=o.messages,
        response=o.response,
        success=o.success,
        success_reason=o.success_reason,
        detector_score=o.detector_score,
        detector_flagged=o.detector_flagged,
        judge_rationale=o.judge_rationale,
        latency_ms=o.latency_ms,
        trace_id=o.trace_id,
    )


def persist_report(session: Session, run: RedteamRun, report: RunReport) -> None:
    for o in report.outcomes:
        session.add(_outcome_row(run.id, o))
    run.total_probes = report.total
    run.successes = report.successes
    run.asr = report.asr
    run.detector_caught = report.detector_caught
    run.finished_at = datetime.now(UTC)
    session.add(run)
    session.commit()


def import_report(engine: Engine, payload: dict[str, Any]) -> RedteamRun:
    report = RunReport.model_validate(payload["report"])
    with Session(engine) as session:
        run = RedteamRun(
            app=payload["app"],
            target=payload["target"],
            git_sha=payload.get("git_sha"),
            defence=payload.get("defence"),
            config_json=payload.get("config", {}),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        persist_report(session, run, report)
        session.refresh(run)
        return run


async def execute_run(run_id: UUID) -> dict[str, Any]:
    """Run the probes recorded in ``run.config_json`` against the target (Celery path)."""
    settings = get_settings()
    engine = engine_for(settings.postgres_dsn)
    with Session(engine) as session:
        run = session.get(RedteamRun, run_id)
        if run is None:
            return {"run_id": str(run_id), "status": "missing"}
        cfg = run.config_json
        judge = None
        if cfg.get("judge_tier"):
            from lens_core.judges.router import JudgeRouter

            judge = JudgeRouter.from_env().get(cfg["judge_tier"])
        probes = load_probes(Path(cfg.get("probes", "data/probes")))
        if cfg.get("categories"):
            probes = [p for p in probes if p.category in cfg["categories"]]
        runner = RedteamRunner(
            HttpTarget(run.target), judge=judge, mutators=cfg.get("mutators", [])
        )
        report = await runner.run(probes)
        persist_report(session, run, report)
    return {
        "run_id": str(run_id),
        "asr": report.asr,
        "total": report.total,
        "successes": report.successes,
    }


def asr_over_time(session: Session, app: str, category: str | None = None) -> list[dict[str, Any]]:
    runs = session.exec(
        select(RedteamRun)
        .where(RedteamRun.app == app, RedteamRun.finished_at.is_not(None))
        .order_by(RedteamRun.started_at)  # type: ignore[union-attr]
    ).all()
    points: list[dict[str, Any]] = []
    for run in runs:
        if category:
            rows = session.exec(
                select(ProbeResult).where(
                    ProbeResult.run_id == run.id, ProbeResult.category == category
                )
            ).all()
            total = len(rows)
            succ = sum(1 for r in rows if r.success)
            asr = succ / total if total else 0.0
        else:
            total, succ, asr = run.total_probes, run.successes, run.asr
        points.append(
            {
                "run_id": str(run.id),
                "git_sha": run.git_sha,
                "defence": run.defence,
                "started_at": run.started_at.isoformat(),
                "total": total,
                "successes": succ,
                "asr": asr,
            }
        )
    return points
