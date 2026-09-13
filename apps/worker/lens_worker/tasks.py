"""Celery tasks. Bodies land in phases 3 (eval) and 5 (red team); signatures are fixed now."""

from __future__ import annotations

from typing import Any

from lens_worker.celery_app import app


@app.task(name="lens.ping")
def ping() -> str:
    return "pong"


@app.task(name="lens.evaluate_trace", bind=True)
def evaluate_trace(self: Any, trace_id: str, metrics: list[str] | None = None) -> dict[str, Any]:
    """Online evaluation of one ingested trace (SPEC.md §5.4)."""
    return {"trace_id": trace_id, "metrics": metrics or [], "status": "not_implemented", "phase": 3}


@app.task(name="lens.run_dataset_eval", bind=True)
def run_dataset_eval(self: Any, run_id: str) -> dict[str, Any]:
    """Offline evaluation of a dataset (SPEC.md §5.4)."""
    return {"run_id": run_id, "status": "not_implemented", "phase": 3}


@app.task(name="lens.run_redteam", bind=True)
def run_redteam(self: Any, run_id: str) -> dict[str, Any]:
    """Red-team run against a target (SPEC.md §6)."""
    return {"run_id": run_id, "status": "not_implemented", "phase": 5}
