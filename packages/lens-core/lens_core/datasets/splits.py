"""Deterministic train/dev/test splits (SPEC.md §7.1: split by source document to avoid leakage)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from lens_core.datasets.schema import ExampleRecord, Split, SplitStrategy

SOURCE_KEYS = ("source_document", "document_id", "doc_id", "source")


def _bucket(key: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()
    return int(digest[:12], 16) / 16**12


def _source_key(r: ExampleRecord, index: int) -> str:
    for k in SOURCE_KEYS:
        v = r.metadata.get(k)
        if v:
            return str(v)
    if r.contexts:
        return r.contexts[0][:200]
    return r.id or str(index)


def assign_splits(
    records: Sequence[ExampleRecord],
    *,
    strategy: SplitStrategy = "random",
    ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
    seed: int = 13,
) -> list[ExampleRecord]:
    """Return copies with ``split`` set. ``manual`` keeps existing splits."""
    if strategy == "manual":
        return list(records)
    train, dev, _ = ratios
    out: list[ExampleRecord] = []
    for i, r in enumerate(records):
        key = _source_key(r, i) if strategy == "by_source_document" else (r.id or str(i))
        u = _bucket(key, seed)
        split: Split = "train" if u < train else "dev" if u < train + dev else "test"
        out.append(r.model_copy(update={"split": split}))
    return out


def split_counts(records: Sequence[ExampleRecord]) -> dict[str, int]:
    counts = {"train": 0, "dev": 0, "test": 0}
    for r in records:
        counts[r.split] = counts.get(r.split, 0) + 1
    return counts
