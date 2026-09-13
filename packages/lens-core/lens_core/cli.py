"""``lens`` command-line interface (SPEC.md §2.1: ingest|eval|redteam|label|ci|serve)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import httpx
import typer

from lens_core import __version__

app = typer.Typer(
    name="lens",
    help="Lens: LLM evaluation & observability framework.",
    no_args_is_help=True,
    add_completion=False,
)

_NOT_YET = "not implemented yet: scheduled for phase {phase} (see SPEC.md §10)."


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


@app.command(name="eval")
def eval_cmd() -> None:
    """Run an offline evaluation of an app over a dataset."""
    typer.secho(_NOT_YET.format(phase=3), fg="yellow", err=True)
    raise typer.Exit(code=2)


@app.command()
def redteam() -> None:
    """Attack a target with the probe library and report ASR."""
    typer.secho(_NOT_YET.format(phase=5), fg="yellow", err=True)
    raise typer.Exit(code=2)


@app.command()
def label() -> None:
    """Label traces/examples from the terminal."""
    typer.secho(_NOT_YET.format(phase=4), fg="yellow", err=True)
    raise typer.Exit(code=2)


@app.command()
def ci() -> None:
    """Gate CI on metric regressions against a baseline."""
    typer.secho(_NOT_YET.format(phase=8), fg="yellow", err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":  # pragma: no cover
    app()
