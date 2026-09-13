"""Dataset IO: JSONL in/out with tolerant key aliases (RAGAS / DeepEval / HaluEval style)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lens_core.datasets.schema import ExampleRecord

INPUT_KEYS = ("input", "question", "query", "prompt", "user_input")
OUTPUT_KEYS = ("output", "answer", "response", "actual_output", "completion")
EXPECTED_KEYS = ("expected_output", "ground_truth", "reference", "expected", "ideal")
CONTEXT_KEYS = ("contexts", "context", "retrieved_contexts", "retrieval_context", "passages")


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def record_from_dict(d: dict[str, Any], *, index: int | None = None) -> ExampleRecord:
    inp = _first(d, INPUT_KEYS)
    if inp is None:
        raise ValueError(
            f"record {index if index is not None else ''} has no input field ({INPUT_KEYS})"
        )
    ctx = _first(d, CONTEXT_KEYS)
    if isinstance(ctx, str):
        ctx = [ctx]
    if isinstance(ctx, list):
        ctx = [
            c if isinstance(c, str) else str(c.get("text", c)) if isinstance(c, dict) else str(c)
            for c in ctx
        ]
    known = set(INPUT_KEYS + OUTPUT_KEYS + EXPECTED_KEYS + CONTEXT_KEYS) | {
        "id",
        "expected_tools",
        "metadata",
        "split",
        "source_trace_id",
    }
    extra = {k: v for k, v in d.items() if k not in known}
    return ExampleRecord(
        id=str(d["id"]) if d.get("id") is not None else (str(index) if index is not None else None),
        input=str(inp),
        output=(str(_first(d, OUTPUT_KEYS)) if _first(d, OUTPUT_KEYS) is not None else None),
        expected_output=(
            str(_first(d, EXPECTED_KEYS)) if _first(d, EXPECTED_KEYS) is not None else None
        ),
        contexts=list(ctx or []),
        expected_tools=d.get("expected_tools"),
        metadata={**(d.get("metadata") or {}), **extra},
        split=d.get("split", "train"),
        source_trace_id=d.get("source_trace_id"),
    )


def load_jsonl(path: Path) -> list[ExampleRecord]:
    records: list[ExampleRecord] = []
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            records.append(record_from_dict(json.loads(line), index=i))
    return records


def save_jsonl(path: Path, records: Iterable[ExampleRecord]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(r.model_dump_json(exclude_none=True) + "\n")
            n += 1
    return n
