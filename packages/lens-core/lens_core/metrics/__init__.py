"""Evaluation metrics (SPEC.md §5): interface, registry, engine and built-ins."""

from lens_core.metrics.base import BaseMetric, EvalItem, ExpectedTool, Metric, MetricResult
from lens_core.metrics.engine import Engine, ItemResults, ResultCache, RunSummary
from lens_core.metrics.registry import (
    MetricSpec,
    get_metric,
    list_metrics,
    load_metric_module,
    metric_specs,
    register_metric,
)

__all__ = [
    "BaseMetric",
    "Engine",
    "EvalItem",
    "ExpectedTool",
    "ItemResults",
    "Metric",
    "MetricResult",
    "MetricSpec",
    "ResultCache",
    "RunSummary",
    "get_metric",
    "list_metrics",
    "load_metric_module",
    "metric_specs",
    "register_metric",
]
