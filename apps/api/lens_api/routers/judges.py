"""Judge quality API (SPEC.md §5.3, §8 page 4): agreement with humans and between judges,
calibration fitting/storage, per-judge cost and latency."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from lens_api.db import get_session
from lens_api.deps import require_api_key
from lens_api.models.sql import HumanLabel, JudgeCalibration, Score
from lens_core.judges.agreement import AgreementReport, agreement
from lens_core.judges.calibration import (
    CalibrationReport,
    IsotonicCalibrator,
    TemperatureScaler,
    calibrate,
)
from lens_core.judges.prompts import list_prompts

router = APIRouter(prefix="/judges", tags=["judges"], dependencies=[Depends(require_api_key)])

Key = tuple[str | None, UUID | None]


class JudgeCost(BaseModel):
    judge_model: str
    metric: str
    n: int
    cost_per_1k_usd: float
    p50_latency_ms: float
    p95_latency_ms: float


class QualityOut(BaseModel):
    vs_human: list[AgreementReport]
    between_judges: list[AgreementReport]
    inter_annotator: list[AgreementReport]
    costs: list[JudgeCost]
    judges: list[str]
    metrics: list[str]
    human_labels: int


class CalibrateIn(BaseModel):
    judge_model: str
    metric: str


class CalibrationOut(BaseModel):
    id: UUID
    judge_model: str
    metric: str
    method: str
    params: dict[str, Any]
    n: int
    brier_raw: float
    brier_calibrated: float
    created_at: datetime


class PromptOut(BaseModel):
    name: str
    version: str
    output: str
    variables: list[str] = Field(default_factory=list)


def _latest_scores(session: Session, metric: str | None) -> dict[str, dict[str, dict[Key, Score]]]:
    """metric -> judge_model -> item key -> latest non-skipped score."""
    q = select(Score).where(Score.skipped.is_(False), Score.error.is_(None))
    if metric:
        q = q.where(Score.metric == metric)
    out: dict[str, dict[str, dict[Key, Score]]] = defaultdict(lambda: defaultdict(dict))
    for s in session.exec(q).all():
        key: Key = (s.trace_id, s.example_id)
        judge = s.judge_model or "unknown"
        prev = out[s.metric][judge].get(key)
        if prev is None or s.created_at > prev.created_at:
            out[s.metric][judge][key] = s
    return out


def _human_means(session: Session, metric: str | None) -> dict[str, dict[Key, float]]:
    q = select(HumanLabel)
    if metric:
        q = q.where(HumanLabel.metric == metric)
    acc: dict[str, dict[Key, list[float]]] = defaultdict(lambda: defaultdict(list))
    for lab in session.exec(q).all():
        acc[lab.metric][(lab.trace_id, lab.example_id)].append(lab.value)
    return {m: {k: sum(v) / len(v) for k, v in items.items()} for m, items in acc.items()}


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


def _inter_annotator(session: Session, metric: str | None) -> list[AgreementReport]:
    """Cohen's kappa between each pair of labellers on items both scored (SPEC.md §13)."""
    q = select(HumanLabel)
    if metric:
        q = q.where(HumanLabel.metric == metric)
    # metric -> labeller -> item key -> value (latest wins)
    by: dict[str, dict[str, dict[Key, float]]] = defaultdict(lambda: defaultdict(dict))
    for lab in session.exec(q).all():
        by[lab.metric][lab.labeller][(lab.trace_id, lab.example_id)] = lab.value
    out: list[AgreementReport] = []
    for m, per_labeller in by.items():
        names = sorted(per_labeller)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                common = sorted(set(per_labeller[a]) & set(per_labeller[b]), key=str)
                if len(common) >= 2:
                    out.append(
                        agreement(
                            m,
                            a,
                            [per_labeller[a][k] for k in common],
                            b,
                            [per_labeller[b][k] for k in common],
                        )
                    )
    return out


@router.get("/quality", response_model=QualityOut)
def quality(
    session: Annotated[Session, Depends(get_session)], metric: str | None = None
) -> QualityOut:
    scores = _latest_scores(session, metric)
    humans = _human_means(session, metric)
    vs_human: list[AgreementReport] = []
    between: list[AgreementReport] = []
    costs: list[JudgeCost] = []
    judges: set[str] = set()
    for m, by_judge in scores.items():
        judge_names = sorted(by_judge)
        judges.update(judge_names)
        for j in judge_names:
            items = by_judge[j]
            paired = [
                (s.value, humans[m][k]) for k, s in items.items() if m in humans and k in humans[m]
            ]
            if paired:
                vs_human.append(
                    agreement(m, j, [p[0] for p in paired], "human", [p[1] for p in paired])
                )
            costs.append(
                JudgeCost(
                    judge_model=j,
                    metric=m,
                    n=len(items),
                    cost_per_1k_usd=round(
                        sum(s.cost_usd or 0.0 for s in items.values()) / len(items) * 1000, 4
                    ),
                    p50_latency_ms=_percentile([s.latency_ms or 0.0 for s in items.values()], 0.5),
                    p95_latency_ms=_percentile([s.latency_ms or 0.0 for s in items.values()], 0.95),
                )
            )
        for i, a in enumerate(judge_names):
            for b in judge_names[i + 1 :]:
                common = set(by_judge[a]) & set(by_judge[b])
                if common:
                    keys = sorted(common, key=str)
                    between.append(
                        agreement(
                            m,
                            a,
                            [by_judge[a][k].value for k in keys],
                            b,
                            [by_judge[b][k].value for k in keys],
                        )
                    )
    n_labels = len(session.exec(select(HumanLabel)).all())
    return QualityOut(
        vs_human=vs_human,
        between_judges=between,
        inter_annotator=_inter_annotator(session, metric),
        costs=costs,
        judges=sorted(judges),
        metrics=sorted(scores),
        human_labels=n_labels,
    )


@router.post("/calibrate", response_model=CalibrationReport)
def fit_calibration(
    body: CalibrateIn, session: Annotated[Session, Depends(get_session)]
) -> CalibrationReport:
    scores = _latest_scores(session, body.metric).get(body.metric, {}).get(body.judge_model, {})
    humans = _human_means(session, body.metric).get(body.metric, {})
    paired = [(s.value, humans[k]) for k, s in scores.items() if k in humans]
    if len(paired) < 5:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"need ≥5 human-labelled items, have {len(paired)}"
        )
    predicted, observed = [p[0] for p in paired], [p[1] for p in paired]
    report = calibrate(body.judge_model, body.metric, predicted, observed)
    ts = TemperatureScaler.fit(predicted, observed)
    iso = IsotonicCalibrator.fit(predicted, observed)
    for method, params, brier in (
        ("temperature", ts.model_dump(), report.brier_temperature),
        ("isotonic", iso.model_dump(), report.brier_isotonic),
    ):
        session.add(
            JudgeCalibration(
                judge_model=body.judge_model,
                metric=body.metric,
                method=method,
                params=params,
                n=len(paired),
                brier_raw=report.brier_raw,
                brier_calibrated=brier,
            )
        )
    session.commit()
    return report


@router.get("/calibrations", response_model=list[CalibrationOut])
def list_calibrations(session: Annotated[Session, Depends(get_session)]) -> list[CalibrationOut]:
    rows = session.exec(select(JudgeCalibration).order_by(JudgeCalibration.created_at.desc())).all()  # type: ignore[attr-defined]
    return [CalibrationOut.model_validate(r.model_dump()) for r in rows]


@router.get("/prompts", response_model=list[PromptOut])
def prompts() -> list[PromptOut]:
    return [
        PromptOut(name=p.name, version=p.version, output=p.output, variables=sorted(p.variables))
        for p in list_prompts()
    ]
