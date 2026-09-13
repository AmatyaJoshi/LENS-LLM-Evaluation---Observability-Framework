"""CLI entry for ``lens redteam`` (SPEC.md §6). Wires probes → mutators → target → scoring → API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import typer

from lens_core.redteam.probes import load_probes
from lens_core.redteam.runner import RedteamRunner, RunReport
from lens_core.redteam.targets import HttpTarget


def run_redteam_cli(
    *,
    target: str,
    app_name: str,
    probes: Path,
    categories: list[str] | None,
    mutators: list[str],
    sha: str | None,
    defence: str | None,
    judge_tier: str | None,
    endpoint: str,
    api_key: str | None,
    out: Path | None,
    local: bool,
    concurrency: int,
) -> RunReport:
    library = load_probes(probes)
    if categories:
        library = [p for p in library if p.category in categories]
    if not library:
        raise typer.BadParameter("no probes selected")
    judge = None
    if judge_tier:
        from lens_core.judges.router import JudgeRouter

        judge = JudgeRouter.from_env().get(judge_tier)
    runner = RedteamRunner(
        HttpTarget(target), judge=judge, mutators=mutators, concurrency=concurrency
    )
    typer.echo(f"running {len(library)} probes × {1 + len(mutators)} variants against {target}")
    report = asyncio.run(runner.run(library))

    typer.echo("")
    typer.echo(f"{'category':<26}{'probes':>8}{'success':>9}{'ASR':>8}")
    for cat, stats in sorted(report.by_category.items()):
        typer.echo(f"{cat:<26}{stats['total']:>8}{stats['successes']:>9}{stats['asr']:>8.1%}")
    typer.echo(
        f"\noverall ASR {report.asr:.1%} ({report.successes}/{report.total}); detector caught {report.detector_caught}"
    )

    payload: dict[str, Any] = {
        "app": app_name,
        "target": target,
        "git_sha": sha,
        "defence": defence,
        "config": {
            "probes": str(probes),
            "categories": categories,
            "mutators": mutators,
            "judge_tier": judge_tier,
        },
        "report": report.model_dump(mode="json"),
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if not local:
        headers = {"x-lens-api-key": api_key} if api_key else {}
        try:
            r = httpx.post(
                f"{endpoint.rstrip('/')}/redteam/runs/import",
                json=payload,
                headers=headers,
                timeout=120.0,
            )
            r.raise_for_status()
            typer.echo(f"run {r.json()['id']} stored at {endpoint}")
        except httpx.HTTPError as exc:
            typer.secho(f"could not store run in API: {exc}", fg="yellow", err=True)
    return report
