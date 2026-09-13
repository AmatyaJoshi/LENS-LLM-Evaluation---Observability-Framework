"""Human labels API (SPEC.md §8 page 6): create/list labels and the disagreement-first queue."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from lens_api.db import get_session
from lens_api.deps import get_store, require_api_key
from lens_api.models.clickhouse import SpanStore
from lens_api.models.sql import Example, HumanLabel, Score

router = APIRouter(prefix="/labels", tags=["labels"], dependencies=[Depends(require_api_key)])


class LabelIn(BaseModel):
    trace_id: str | None = None
    example_id: UUID | None = None
    metric: str
    value: float = Field(ge=0.0, le=1.0)
    labeller: str = Field(min_length=1, max_length=80)
    notes: str | None = None

    @model_validator(mode="after")
    def _one_target(self) -> LabelIn:
        if bool(self.trace_id) == bool(self.example_id):
            raise ValueError("provide exactly one of trace_id or example_id")
        return self


class LabelOut(BaseModel):
    id: UUID
    trace_id: str | None
    example_id: UUID | None
    metric: str
    value: float
    labeller: str
    notes: str | None
    created_at: datetime


class QueueItem(BaseModel):
    trace_id: str | None
    example_id: UUID | None
    metric: str
    priority: float  # judge disagreement (max − min); 0 when a single judge scored it
    judge_scores: list[dict[str, Any]]
    human_labels: int
    input: str | None = None
    output: str | None = None
    contexts: list[str] = Field(default_factory=list)


@router.post("", response_model=LabelOut, status_code=201)
def create_label(body: LabelIn, session: Annotated[Session, Depends(get_session)]) -> LabelOut:
    if body.example_id and not session.get(Example, body.example_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "example not found")
    label = HumanLabel(**body.model_dump())
    session.add(label)
    session.commit()
    session.refresh(label)
    return LabelOut.model_validate(label.model_dump())


@router.get("", response_model=list[LabelOut])
def list_labels(
    session: Annotated[Session, Depends(get_session)],
    metric: str | None = None,
    trace_id: str | None = None,
    example_id: UUID | None = None,
    labeller: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[LabelOut]:
    q = select(HumanLabel)
    if metric:
        q = q.where(HumanLabel.metric == metric)
    if trace_id:
        q = q.where(HumanLabel.trace_id == trace_id)
    if example_id:
        q = q.where(HumanLabel.example_id == example_id)
    if labeller:
        q = q.where(HumanLabel.labeller == labeller)
    rows = session.exec(q.order_by(HumanLabel.created_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return [LabelOut.model_validate(r.model_dump()) for r in rows]


@router.get("/queue", response_model=list[QueueItem])
async def label_queue(
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[SpanStore, Depends(get_store)],
    metric: str,
    labeller: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> list[QueueItem]:
    """Items to label next: highest judge disagreement first, then unlabelled scored items
    (active-learning-style prioritisation, SPEC.md §8 page 6)."""
    scores = session.exec(
        select(Score).where(Score.metric == metric, Score.skipped.is_(False), Score.error.is_(None))
    ).all()
    grouped: dict[tuple[str | None, UUID | None], dict[str, Score]] = defaultdict(dict)
    for s in scores:
        key = (s.trace_id, s.example_id)
        # keep the latest score per judge model
        prev = grouped[key].get(s.judge_model or "unknown")
        if prev is None or s.created_at > prev.created_at:
            grouped[key][s.judge_model or "unknown"] = s

    labels = session.exec(select(HumanLabel).where(HumanLabel.metric == metric)).all()
    label_counts: dict[tuple[str | None, UUID | None], int] = defaultdict(int)
    labelled_by_me: set[tuple[str | None, UUID | None]] = set()
    for lab in labels:
        label_counts[(lab.trace_id, lab.example_id)] += 1
        if labeller and lab.labeller == labeller:
            labelled_by_me.add((lab.trace_id, lab.example_id))

    candidates: list[QueueItem] = []
    for key, by_judge in grouped.items():
        if key in labelled_by_me:
            continue
        values = [s.value for s in by_judge.values()]
        priority = (max(values) - min(values)) if len(values) > 1 else 0.0
        candidates.append(
            QueueItem(
                trace_id=key[0],
                example_id=key[1],
                metric=metric,
                priority=priority,
                judge_scores=[
                    {
                        "judge_model": j,
                        "value": s.value,
                        "rationale": s.rationale,
                        "judge_tier": s.judge_tier,
                    }
                    for j, s in by_judge.items()
                ],
                human_labels=label_counts.get(key, 0),
            )
        )
    candidates.sort(key=lambda c: (-c.priority, c.human_labels, str(c.trace_id or c.example_id)))
    out = candidates[:limit]

    # attach content for the labelling UI
    for item in out:
        if item.example_id:
            ex = session.get(Example, item.example_id)
            if ex:
                item.input, item.output, item.contexts = (
                    ex.input,
                    ex.output,
                    list(ex.contexts or []),
                )
        elif item.trace_id:
            spans = await store.get_trace(item.trace_id)
            if spans:
                from lens_api.ingest import normalize
                from lens_core.trace import build_trajectory

                t = build_trajectory(spans, normalize.derive(spans))
                item.input, item.output = t.user_input, t.final_output
                item.contexts = [d.text for r in t.retrievals for d in r.documents if d.text]
    return out
