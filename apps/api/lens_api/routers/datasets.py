"""Datasets API (SPEC.md §3.2, §8 page 7): CRUD, bulk examples, promote traces, splits."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from lens_api.db import get_session
from lens_api.deps import get_store, require_api_key
from lens_api.ingest import normalize
from lens_api.models.clickhouse import SpanStore
from lens_api.models.sql import Dataset, Example
from lens_api.services.evaluation import example_to_record
from lens_core.datasets.schema import ExampleRecord, SplitStrategy
from lens_core.datasets.splits import assign_splits
from lens_core.trace import build_trajectory

router = APIRouter(prefix="/datasets", tags=["datasets"], dependencies=[Depends(require_api_key)])


class DatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    split_strategy: SplitStrategy = "random"


class DatasetOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    split_strategy: str
    created_at: Any
    example_count: int = 0
    splits: dict[str, int] = Field(default_factory=dict)


class ExamplesIn(BaseModel):
    examples: list[ExampleRecord]


class PromoteIn(BaseModel):
    trace_ids: list[str]
    expected_outputs: dict[str, str] = Field(default_factory=dict)
    split: str | None = None


class SplitIn(BaseModel):
    strategy: SplitStrategy = "random"
    ratios: tuple[float, float, float] = (0.8, 0.1, 0.1)
    seed: int = 13


class ExamplePage(BaseModel):
    items: list[dict[str, Any]]
    total: int


def _counts(session: Session, dataset_id: UUID) -> tuple[int, dict[str, int]]:
    rows = session.exec(
        select(Example.split, func.count())
        .where(Example.dataset_id == dataset_id)
        .group_by(Example.split)
    ).all()
    splits = {str(s): int(n) for s, n in rows}
    return sum(splits.values()), splits


def _out(session: Session, d: Dataset) -> DatasetOut:
    total, splits = _counts(session, d.id)
    return DatasetOut(
        id=d.id,
        name=d.name,
        description=d.description,
        split_strategy=d.split_strategy,
        created_at=d.created_at,
        example_count=total,
        splits=splits,
    )


def _get(session: Session, dataset_id: UUID) -> Dataset:
    d = session.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    return d


def _example_from_record(dataset_id: UUID, r: ExampleRecord) -> Example:
    return Example(
        dataset_id=dataset_id,
        external_id=r.id,
        input=r.input,
        output=r.output,
        expected_output=r.expected_output,
        contexts=r.contexts or None,
        expected_tools=[t.model_dump() for t in r.expected_tools] if r.expected_tools else None,
        metadata_=r.metadata,
        split=r.split,
        source_trace_id=r.source_trace_id,
    )


@router.get("", response_model=list[DatasetOut])
def list_datasets(session: Annotated[Session, Depends(get_session)]) -> list[DatasetOut]:
    return [
        _out(session, d)
        for d in session.exec(select(Dataset).order_by(Dataset.created_at.desc())).all()
    ]  # type: ignore[attr-defined]


@router.post("", response_model=DatasetOut, status_code=201)
def create_dataset(
    body: DatasetIn, session: Annotated[Session, Depends(get_session)]
) -> DatasetOut:
    if session.exec(select(Dataset).where(Dataset.name == body.name)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "dataset name already exists")
    d = Dataset(name=body.name, description=body.description, split_strategy=body.split_strategy)
    session.add(d)
    session.commit()
    session.refresh(d)
    return _out(session, d)


@router.get("/by-name/{name}", response_model=DatasetOut)
def get_by_name(name: str, session: Annotated[Session, Depends(get_session)]) -> DatasetOut:
    d = session.exec(select(Dataset).where(Dataset.name == name)).first()
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    return _out(session, d)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: UUID, session: Annotated[Session, Depends(get_session)]) -> DatasetOut:
    return _out(session, _get(session, dataset_id))


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: UUID, session: Annotated[Session, Depends(get_session)]) -> None:
    d = _get(session, dataset_id)
    for e in session.exec(select(Example).where(Example.dataset_id == dataset_id)).all():
        session.delete(e)
    session.delete(d)
    session.commit()


@router.post("/{dataset_id}/examples")
def add_examples(
    dataset_id: UUID, body: ExamplesIn, session: Annotated[Session, Depends(get_session)]
) -> dict[str, int]:
    _get(session, dataset_id)
    for r in body.examples:
        session.add(_example_from_record(dataset_id, r))
    session.commit()
    return {"inserted": len(body.examples)}


@router.get("/{dataset_id}/examples", response_model=ExamplePage)
def list_examples(
    dataset_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    split: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExamplePage:
    _get(session, dataset_id)
    q = select(Example).where(Example.dataset_id == dataset_id)
    if split:
        q = q.where(Example.split == split)
    total = session.exec(select(func.count()).select_from(q.subquery())).one()
    rows = session.exec(q.order_by(Example.created_at).offset(offset).limit(limit)).all()  # type: ignore[arg-type]
    items = []
    for e in rows:
        rec = example_to_record(e).model_dump()
        rec["example_id"] = str(e.id)
        items.append(rec)
    return ExamplePage(items=items, total=int(total))


@router.post("/{dataset_id}/promote")
async def promote_traces(
    dataset_id: UUID,
    body: PromoteIn,
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[SpanStore, Depends(get_store)],
) -> dict[str, Any]:
    """Promote ingested traces into dataset examples (SPEC.md §8 page 7)."""
    _get(session, dataset_id)
    inserted, missing = 0, []
    for tid in body.trace_ids:
        spans = await store.get_trace(tid)
        if not spans:
            missing.append(tid)
            continue
        t = build_trajectory(spans, normalize.derive(spans))
        rec = ExampleRecord.from_trajectory(t, expected_output=body.expected_outputs.get(tid))
        if body.split:
            rec = rec.model_copy(update={"split": body.split})
        session.add(_example_from_record(dataset_id, rec))
        inserted += 1
    session.commit()
    return {"inserted": inserted, "missing": missing}


@router.post("/{dataset_id}/split")
def resplit(
    dataset_id: UUID, body: SplitIn, session: Annotated[Session, Depends(get_session)]
) -> dict[str, int]:
    d = _get(session, dataset_id)
    rows = session.exec(select(Example).where(Example.dataset_id == dataset_id)).all()
    records = [example_to_record(e) for e in rows]
    assigned = assign_splits(records, strategy=body.strategy, ratios=body.ratios, seed=body.seed)
    for e, r in zip(rows, assigned, strict=True):
        e.split = r.split
        session.add(e)
    d.split_strategy = body.strategy
    session.add(d)
    session.commit()
    return _counts(session, dataset_id)[1]
