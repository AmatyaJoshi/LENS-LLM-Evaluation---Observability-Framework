"""``lens`` command-line interface (SPEC.md §2.1: ingest|eval|redteam|label|ci|serve)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from lens_core import __version__

app = typer.Typer(
    name="lens",
    help="Lens: LLM evaluation & observability framework.",
    no_args_is_help=True,
    add_completion=False,
)

DEFAULT_METRICS = "faithfulness,answer_relevance,context_precision,context_recall,hallucination"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"lens {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Lens CLI."""


# ---------------------------------------------------------------------------------------------
# API client helpers
# ---------------------------------------------------------------------------------------------


class Api:
    def __init__(self, endpoint: str, api_key: str | None) -> None:
        self.base = endpoint.rstrip("/")
        headers = {"x-lens-api-key": api_key} if api_key else {}
        self.client = httpx.Client(base_url=self.base, headers=headers, timeout=60.0)

    def get(self, path: str, **params: Any) -> Any:
        r = self.client.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: Any) -> Any:
        r = self.client.post(path, json=body)
        r.raise_for_status()
        return r.json() if r.content else None

    def reachable(self) -> bool:
        try:
            return self.client.get("/health").status_code == 200
        except httpx.HTTPError:
            return False


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return os.environ.get("GITHUB_SHA", "")[:12] or None


# ---------------------------------------------------------------------------------------------
# ingest / serve
# ---------------------------------------------------------------------------------------------


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(help="OTLP/JSON trace export file (.json)")],
    endpoint: Annotated[
        str, typer.Option(envvar="LENS_ENDPOINT", help="Lens API base URL")
    ] = "http://localhost:8000",
    api_key: Annotated[str | None, typer.Option(envvar="LENS_API_KEY")] = None,
) -> None:
    """Send a recorded OTLP/JSON trace file to the Lens ingest endpoint."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    headers = {"content-type": "application/json"}
    if api_key:
        headers["x-lens-api-key"] = api_key
    resp = httpx.post(f"{endpoint.rstrip('/')}/v1/traces", json=payload, headers=headers)
    if resp.status_code >= 400:
        typer.secho(f"ingest failed: {resp.status_code} {resp.text}", fg="red", err=True)
        raise typer.Exit(code=1)
    typer.echo(resp.text)


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "0.0.0.0",
    port: Annotated[int, typer.Option()] = 8000,
    reload: Annotated[bool, typer.Option()] = False,
) -> None:
    """Run the Lens API (requires the lens-api package)."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        typer.secho("uvicorn / lens-api not installed", fg="red", err=True)
        raise typer.Exit(code=1) from exc
    uvicorn.run("lens_api.main:app", host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------------------------


def _load_records(dataset: str, api: Api | None) -> tuple[list[Any], str | None]:
    """Return (records, dataset_id). ``dataset`` is a .jsonl path or a dataset name in the API."""
    from lens_core.datasets import load_jsonl

    p = Path(dataset)
    if p.exists():
        return load_jsonl(p), None
    if api is None or not api.reachable():
        raise typer.BadParameter(f"{dataset!r} is neither a file nor reachable via the API")
    from lens_core.datasets.schema import ExampleRecord

    ds = api.get(f"/datasets/by-name/{dataset}")
    page = api.get(f"/datasets/{ds['id']}/examples", limit=1000)
    records = []
    for item in page["items"]:
        rec = ExampleRecord.model_validate({k: v for k, v in item.items() if k != "example_id"})
        rec.metadata["example_id"] = item["example_id"]
        records.append(rec)
    return records, ds["id"]


def _call_target(target: str, record: Any, timeout: float) -> dict[str, Any]:
    """POST {input, id} to the target app; expects {output, contexts?, trace_id?}."""
    r = httpx.post(target, json={"input": record.input, "id": record.id}, timeout=timeout)
    r.raise_for_status()
    data: dict[str, Any] = r.json()
    if "output" not in data:
        raise typer.BadParameter(f"target response lacks 'output': {str(data)[:200]}")
    return data


def run_eval(
    *,
    dataset: str,
    app_name: str,
    sha: str | None,
    metrics: list[str],
    judge_tier: str,
    target: str | None,
    endpoint: str,
    api_key: str | None,
    concurrency: int,
    out: Path | None,
    local: bool,
    mode: str = "offline",
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    from lens_core.judges.router import JudgeRouter
    from lens_core.metrics import Engine, ResultCache
    from lens_core.trace.model import Trajectory

    api = None if local else Api(endpoint, api_key)
    records, dataset_id = _load_records(dataset, api)
    if not records:
        raise typer.BadParameter("dataset has no examples")

    items = []
    for rec in records:
        trajectory: Trajectory | None = None
        if target:
            data = _call_target(target, rec, timeout=120.0)
            rec = rec.model_copy(update={"output": data["output"]})
            if data.get("contexts"):
                rec = rec.model_copy(update={"contexts": list(data["contexts"])})
            if data.get("trace_id") and api is not None and api.reachable():
                try:
                    trajectory = Trajectory.model_validate(
                        api.get(f"/traces/{data['trace_id']}/trajectory")
                    )
                except httpx.HTTPError:
                    trajectory = None
        if rec.output is None and trajectory is None:
            typer.secho(
                f"skipping {rec.id}: no output (use --target to run the app)", fg="yellow", err=True
            )
            continue
        items.append(rec.to_eval_item(trajectory))

    judge = JudgeRouter.from_env().get(judge_tier)
    engine = Engine(judge, metrics=metrics, concurrency=concurrency, cache=ResultCache(cache_dir))
    typer.echo(
        f"scoring {len(items)} items × {len(metrics)} metrics with {judge.name} ({judge.model})"
    )
    results = asyncio.run(engine.run(items))
    summary = engine.summarise(results)

    run_id: str | None = None
    if api is not None and api.reachable():
        run = api.post(
            "/evals/runs",
            {
                "app": app_name,
                "dataset_id": dataset_id,
                "git_sha": sha,
                "mode": mode,
                "judge_tier": judge_tier,
                "config_json": {
                    "metrics": metrics,
                    "judge_model": judge.model,
                    "dataset": dataset,
                    "target": target,
                },
            },
        )
        run_id = run["id"]
        scores = []
        for rec, ir in zip(
            [r for r in records if r.output is not None or target], results, strict=False
        ):
            for res in ir.results:
                scores.append(
                    {
                        "result": res.model_dump(mode="json"),
                        "trace_id": ir.trace_id,
                        "example_id": rec.metadata.get("example_id"),
                        "judge_tier": judge_tier,
                    }
                )
        for i in range(0, len(scores), 200):
            api.post(f"/evals/runs/{run_id}/scores", {"scores": scores[i : i + 200]})
        api.post(f"/evals/runs/{run_id}/finish", {})

    report = {
        "run_id": run_id,
        "app": app_name,
        "git_sha": sha,
        "dataset": dataset,
        "judge": {"tier": judge_tier, "model": judge.model},
        "summary": summary.model_dump(),
        "items": [ir.model_dump(mode="json") for ir in results],
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    typer.echo("")
    typer.echo(f"{'metric':<24}{'mean':>8}{'skipped':>9}{'errors':>8}")
    for m in metrics:
        typer.echo(
            f"{m:<24}{summary.metrics.get(m, float('nan')):>8.3f}"
            f"{summary.skipped.get(m, 0):>9}{summary.errors.get(m, 0):>8}"
        )
    typer.echo(
        f"\njudge calls {summary.judge_calls}, cost ${summary.cost_usd:.4f}, p95 {summary.p95_judge_latency_ms:.0f} ms"
    )
    if run_id:
        typer.echo(f"run {run_id} stored at {endpoint}")
    return report


@app.command(name="eval")
def eval_cmd(
    dataset: Annotated[
        str, typer.Option("--dataset", help="dataset name in Lens or a .jsonl file")
    ],
    app_name: Annotated[str, typer.Option("--app", help="app under evaluation")],
    sha: Annotated[
        str | None, typer.Option("--sha", help="git sha of the app (default: HEAD)")
    ] = None,
    metrics: Annotated[
        str, typer.Option("--metrics", help="comma-separated metric names")
    ] = DEFAULT_METRICS,
    judge: Annotated[
        str, typer.Option("--judge", help="judge tier: frontier|second_opinion|local")
    ] = "frontier",
    target: Annotated[
        str | None, typer.Option("--target", help="HTTP endpoint of the app to run on each input")
    ] = None,
    endpoint: Annotated[str, typer.Option(envvar="LENS_ENDPOINT")] = "http://localhost:8000",
    api_key: Annotated[str | None, typer.Option(envvar="LENS_API_KEY")] = None,
    concurrency: Annotated[int, typer.Option()] = 4,
    out: Annotated[Path | None, typer.Option("--out", help="write full results JSON here")] = None,
    local: Annotated[bool, typer.Option("--local", help="do not store the run in the API")] = False,
    cache_dir: Annotated[
        Path | None, typer.Option("--cache-dir", help="persist judge results by content hash")
    ] = None,
) -> None:
    """Run an offline evaluation of an app over a dataset (SPEC.md §5.4)."""
    run_eval(
        dataset=dataset,
        app_name=app_name,
        sha=sha or _git_sha(),
        metrics=[m.strip() for m in metrics.split(",") if m.strip()],
        judge_tier=judge,
        target=target,
        endpoint=endpoint,
        api_key=api_key,
        concurrency=concurrency,
        out=out,
        local=local,
        cache_dir=cache_dir,
    )


# ---------------------------------------------------------------------------------------------
# ci
# ---------------------------------------------------------------------------------------------


def parse_thresholds(spec: str) -> dict[str, float]:
    """``"faithfulness:-0.03,hallucination:+0.02"`` → {"faithfulness": -0.03, "hallucination": 0.02}."""
    out: dict[str, float] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition(":")
        out[name.strip()] = float(value)
    return out


def compare(
    current: dict[str, float],
    baseline: dict[str, float],
    thresholds: dict[str, float],
    higher_is_better: dict[str, bool],
    default_tolerance: float = 0.02,
) -> list[dict[str, Any]]:
    """Per-metric regression check.

    A negative threshold is the allowed *drop* for a higher-is-better metric; a positive
    threshold is the allowed *rise* for a lower-is-better metric. Metrics without an explicit
    threshold get ±default_tolerance in the appropriate direction.
    """
    rows: list[dict[str, Any]] = []
    for metric in sorted(set(current) | set(baseline)):
        cur, base = current.get(metric), baseline.get(metric)
        hib = higher_is_better.get(metric, True)
        thr = thresholds.get(metric, -default_tolerance if hib else default_tolerance)
        delta = None if cur is None or base is None else cur - base
        regressed = False
        if delta is not None:
            regressed = delta < thr if thr < 0 else delta > thr
        rows.append(
            {
                "metric": metric,
                "baseline": base,
                "current": cur,
                "delta": delta,
                "threshold": thr,
                "regressed": regressed,
            }
        )
    return rows


def markdown_summary(rows: list[dict[str, Any]], *, title: str) -> str:
    def fmt(v: float | None) -> str:
        return "–" if v is None else f"{v:.3f}"

    lines = [
        f"### {title}",
        "",
        "| Metric | Baseline | Current | Δ | Threshold | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        status = "❌ regression" if r["regressed"] else ("✅" if r["delta"] is not None else "–")
        lines.append(
            f"| {r['metric']} | {fmt(r['baseline'])} | {fmt(r['current'])} | "
            f"{'–' if r['delta'] is None else f'{r["delta"]:+.3f}'} | {r['threshold']:+.3f} | {status} |"
        )
    return "\n".join(lines)


@app.command()
def ci(
    dataset: Annotated[str, typer.Option("--dataset")],
    app_name: Annotated[str, typer.Option("--app")],
    baseline: Annotated[
        str, typer.Option("--baseline", help="baseline run id, git sha, or 'latest'")
    ] = "latest",
    threshold: Annotated[
        str, typer.Option("--threshold", help="e.g. faithfulness:-0.03,hallucination:+0.02")
    ] = "",
    sha: Annotated[str | None, typer.Option("--sha")] = None,
    metrics: Annotated[str, typer.Option("--metrics")] = DEFAULT_METRICS,
    judge: Annotated[str, typer.Option("--judge")] = "frontier",
    target: Annotated[str | None, typer.Option("--target")] = None,
    endpoint: Annotated[str, typer.Option(envvar="LENS_ENDPOINT")] = "http://localhost:8000",
    api_key: Annotated[str | None, typer.Option(envvar="LENS_API_KEY")] = None,
    summary_file: Annotated[Path | None, typer.Option("--summary-file")] = None,
    baseline_file: Annotated[
        Path | None,
        typer.Option(
            "--baseline-file", help="results JSON from a previous `lens eval --out` (offline mode)"
        ),
    ] = None,
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Gate CI: evaluate, compare with a baseline run, exit non-zero on regression (SPEC.md §5.4)."""
    from lens_core.metrics import metric_specs

    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]
    current_sha = sha or _git_sha()
    api = Api(endpoint, api_key)
    online = baseline_file is None and api.reachable()

    report = run_eval(
        dataset=dataset,
        app_name=app_name,
        sha=current_sha,
        metrics=metric_list,
        judge_tier=judge,
        target=target,
        endpoint=endpoint,
        api_key=api_key,
        concurrency=4,
        out=out,
        local=not online,
        mode="ci",
    )
    current = report["summary"]["metrics"]

    baseline_means: dict[str, float] = {}
    baseline_label = baseline
    if baseline_file:
        baseline_means = json.loads(baseline_file.read_text(encoding="utf-8"))["summary"]["metrics"]
        baseline_label = baseline_file.name
    elif online:
        runs = api.get("/evals/runs", app=app_name, limit=200)
        runs = [
            r
            for r in runs
            if r["finished_at"] and r["id"] != report["run_id"] and r.get("dataset_id") is not None
        ]
        chosen = None
        for r in runs:
            if r["id"] == baseline or (r.get("git_sha") and baseline.startswith(r["git_sha"])):
                chosen = r
                break
        if chosen is None and baseline == "latest" and runs:
            chosen = runs[0]
        if chosen:
            baseline_means = chosen["metrics"]
            baseline_label = f"{chosen['id'][:8]} ({chosen.get('git_sha') or 'no sha'})"
    if not baseline_means:
        typer.secho("no baseline run found; recording current run as the new baseline", fg="yellow")

    hib = {s.name: s.higher_is_better for s in metric_specs()}
    rows = compare(current, baseline_means, parse_thresholds(threshold), hib)
    md = markdown_summary(
        rows,
        title=f"Lens evaluation gate: {app_name} @ {current_sha or 'HEAD'} vs {baseline_label}",
    )
    typer.echo("\n" + md)
    if summary_file:
        summary_file.write_text(md + "\n", encoding="utf-8")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(md + "\n")
    regressed = [r["metric"] for r in rows if r["regressed"]]
    if regressed:
        typer.secho(f"\nREGRESSION in {', '.join(regressed)}", fg="red", err=True)
        raise typer.Exit(code=1)
    typer.secho("\nno regressions", fg="green")


# ---------------------------------------------------------------------------------------------
# redteam / label
# ---------------------------------------------------------------------------------------------


@app.command()
def redteam(
    target: Annotated[str, typer.Option("--target", help="HTTP endpoint of the app under test")],
    app_name: Annotated[str, typer.Option("--app")],
    probes: Annotated[Path, typer.Option("--probes", help="probe directory or YAML file")] = Path(
        "data/probes"
    ),
    categories: Annotated[
        str | None, typer.Option("--categories", help="comma-separated subset")
    ] = None,
    mutators: Annotated[
        str, typer.Option("--mutators", help="comma-separated mutators, or 'none'")
    ] = "none",
    sha: Annotated[str | None, typer.Option("--sha")] = None,
    defence: Annotated[
        str | None, typer.Option("--defence", help="label for the defence configuration")
    ] = None,
    judge: Annotated[
        str | None, typer.Option("--judge", help="judge tier for rubric-scored probes")
    ] = None,
    endpoint: Annotated[str, typer.Option(envvar="LENS_ENDPOINT")] = "http://localhost:8000",
    api_key: Annotated[str | None, typer.Option(envvar="LENS_API_KEY")] = None,
    out: Annotated[Path | None, typer.Option("--out")] = None,
    local: Annotated[bool, typer.Option("--local")] = False,
    concurrency: Annotated[int, typer.Option()] = 4,
) -> None:
    """Attack a target with the probe library and report attack success rate (SPEC.md §6)."""
    from lens_core.redteam.cli_runner import run_redteam_cli

    run_redteam_cli(
        target=target,
        app_name=app_name,
        probes=probes,
        categories=[c.strip() for c in categories.split(",")] if categories else None,
        mutators=[]
        if mutators == "none"
        else [m.strip() for m in mutators.split(",") if m.strip()],
        sha=sha or _git_sha(),
        defence=defence,
        judge_tier=judge,
        endpoint=endpoint,
        api_key=api_key,
        out=out,
        local=local,
        concurrency=concurrency,
    )


@app.command()
def label(
    metric: Annotated[str, typer.Option("--metric")],
    labeller: Annotated[str, typer.Option("--labeller", envvar="LENS_LABELLER")],
    endpoint: Annotated[str, typer.Option(envvar="LENS_ENDPOINT")] = "http://localhost:8000",
    api_key: Annotated[str | None, typer.Option(envvar="LENS_API_KEY")] = None,
    limit: Annotated[int, typer.Option()] = 20,
) -> None:
    """Label items from the disagreement queue in the terminal (0-1 score, s=skip, q=quit)."""
    api = Api(endpoint, api_key)
    queue = api.get("/labels/queue", metric=metric, labeller=labeller, limit=limit)
    if not queue:
        typer.echo("queue is empty")
        return
    for i, item in enumerate(queue, 1):
        typer.echo(f"\n[{i}/{len(queue)}] {metric}  disagreement {item['priority']:.2f}")
        typer.echo(f"INPUT:  {(item.get('input') or '')[:500]}")
        typer.echo(f"OUTPUT: {(item.get('output') or '')[:800]}")
        for c in (item.get("contexts") or [])[:3]:
            typer.echo(f"  ctx: {c[:200]}")
        for js in item["judge_scores"]:
            typer.echo(
                f"  judge {js['judge_model']}: {js['value']:.2f}  {js.get('rationale') or ''}"[:200]
            )
        answer = typer.prompt("score 0-1 (s skip, q quit)", default="s")
        if answer.lower().startswith("q"):
            break
        if answer.lower().startswith("s"):
            continue
        try:
            value = float(answer)
        except ValueError:
            typer.secho("not a number, skipped", fg="yellow")
            continue
        api.post(
            "/labels",
            {
                "trace_id": item.get("trace_id"),
                "example_id": item.get("example_id"),
                "metric": metric,
                "value": max(0.0, min(1.0, value)),
                "labeller": labeller,
            },
        )
        typer.secho("saved", fg="green")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
