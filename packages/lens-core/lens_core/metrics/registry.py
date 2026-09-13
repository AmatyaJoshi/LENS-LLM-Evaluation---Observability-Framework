"""Metric registry (SPEC.md §5.1): ``@register_metric`` plus lookup helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from pydantic import BaseModel

from lens_core.metrics.base import BaseMetric

_REGISTRY: dict[str, type[BaseMetric]] = {}


def register_metric[M: type[BaseMetric]](cls: M) -> M:
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} must define a class attribute 'name'")
    _REGISTRY[cls.name] = cls
    return cls


def get_metric(name: str) -> BaseMetric:
    _ensure_builtins()
    try:
        return _REGISTRY[name]()
    except KeyError as exc:
        raise KeyError(f"unknown metric {name!r}; available: {sorted(_REGISTRY)}") from exc


def list_metrics() -> list[str]:
    _ensure_builtins()
    return sorted(_REGISTRY)


class MetricSpec(BaseModel):
    name: str
    version: str
    requires: list[str]
    higher_is_better: bool
    description: str


def metric_specs() -> list[MetricSpec]:
    _ensure_builtins()
    return [
        MetricSpec(
            name=c.name,
            version=c.version,
            requires=sorted(c.requires),
            higher_is_better=c.higher_is_better,
            description=c.description,
        )
        for c in (_REGISTRY[n] for n in sorted(_REGISTRY))
    ]


def load_metric_module(path: Path) -> list[str]:
    """Import a Python file that defines ``@register_metric`` classes; returns new names."""
    before = set(_REGISTRY)
    spec = importlib.util.spec_from_file_location(f"lens_custom_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load metric module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return sorted(set(_REGISTRY) - before)


_loaded = False


def _ensure_builtins() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Importing registers the built-in metrics via the decorator.
    from lens_core.metrics import calibration as _calibration  # noqa: F401
    from lens_core.metrics import (  # noqa: F401
        context_precision,
        context_recall,
        faithfulness,
        hallucination,
        relevance,
        safety,
        task_completion,
        tool_correctness,
        trajectory,
    )
