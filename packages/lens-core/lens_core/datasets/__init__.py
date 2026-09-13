"""Datasets: records, JSONL IO, deterministic splits."""

from lens_core.datasets.loaders import load_jsonl, record_from_dict, save_jsonl
from lens_core.datasets.schema import DatasetSpec, ExampleRecord
from lens_core.datasets.splits import assign_splits, split_counts

__all__ = [
    "DatasetSpec",
    "ExampleRecord",
    "assign_splits",
    "load_jsonl",
    "record_from_dict",
    "save_jsonl",
    "split_counts",
]
