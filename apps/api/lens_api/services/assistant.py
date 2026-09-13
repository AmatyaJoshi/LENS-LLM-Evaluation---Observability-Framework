"""Lens AI Assistant service.

An assistant grounded in the operator's own Lens data. Given a question and an
optional focus (a trace, an eval run, a red-team run, or the overview), it
assembles a compact, factual context bundle from the stores and asks the
frontier LLM to answer *only* from that context. With no LLM key configured it
falls back to a deterministic, template summary of the same bundle, so the
feature degrades gracefully and never fabricates numbers.

Grounding rules (mirrors the metric judges): the model is told to answer only
from the provided Lens data, to cite trace ids / metric names, and to say when
the data does not contain the answer.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlmodel import Session, select

from lens_api.ingest import normalize
from lens_api.models.clickhouse import SpanStore
from lens_api.models.sql import EvalRun, RedteamRun, Score
from lens_api.settings import Settings
from lens_core.judges.router import JudgeRouter
from lens_core.trace import build_trajectory

log = logging.getLogger("lens.assistant")

Focus = Literal["overview", "trace", "eval_run", "redteam_run"]

SYSTEM = """You are Lens Assistant, an expert SRE and ML-evaluation copilot embedded in Lens,
an LLM observability and evaluation platform. You help engineers understand traces, evaluation
scores, judge quality and red-team results for their own LLM applications.

Rules:
- Answer ONLY from the "Lens data" provided below. Do not invent traces, metrics, or numbers.
- When the data does not contain the answer, say so and suggest what to look at next.
- Cite specifics: trace ids (short form), metric names, ASR figures, git shas.
- Be concise and technical. Prefer a direct answer, then a short "why" from the evidence.
- When asked what to do, give concrete next steps a Lens user can take (a filter, a page, a CLI command).
"""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    focus: Focus = "overview"
    trace_id: str | None = None
    run_id: UUID | None = None
    app: str | None = None


class ChatResponse(BaseModel):
    answer: str
    grounded: bool  # True if an LLM answered from context; False for the deterministic fallback
    model: str | None = None
    context_summary: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float = 0.0
    suggestions: list[str] = Field(default_factory=list)


def _clip(text: str | None, n: int = 600) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[: n - 1] + "…"


async def _trace_context(store: SpanStore, engine: Engine, trace_id: str) -> dict[str, Any]:
    spans = await store.get_trace(trace_id)
    if not spans:
        return {"error": f"trace {trace_id} not found"}
    traj = build_trajectory(spans, normalize.derive(spans))
    flagged = [
        {
            "span_id": s.span_id,
            "score": s.attributes.get("lens.security.injection_score"),
            "kind": s.kind,
        }
        for s in spans
        if s.attributes.get("lens.security.flagged")
    ]
    with Session(engine) as session:
        scores = session.exec(select(Score).where(Score.trace_id == trace_id)).all()
    return {
        "trace_id": trace_id,
        "app": traj.app,
        "status": traj.status,
        "user_input": _clip(traj.user_input),
        "final_output": _clip(traj.final_output),
        "steps": len(traj.steps),
        "llm_calls": len(traj.llm_calls),
        "tool_calls": [t.name for t in traj.tool_calls],
        "retrievals": [
            {"query": _clip(r.query, 120), "docs": len(r.documents)} for r in traj.retrievals
        ],
        "total_tokens": traj.total_tokens,
        "duration_ms": round(traj.duration_ms, 1),
        "flagged_spans": flagged,
        "scores": [
            {
                "metric": s.metric,
                "value": round(s.value, 3),
                "rationale": _clip(s.rationale, 200),
                "judge": s.judge_model,
            }
            for s in scores
        ],
    }


def _eval_context(engine: Engine, run_id: UUID) -> dict[str, Any]:
    with Session(engine) as session:
        run = session.get(EvalRun, run_id)
        if not run:
            return {"error": f"run {run_id} not found"}
        scores = session.exec(select(Score).where(Score.run_id == run_id)).all()
    means: dict[str, list[float]] = {}
    for s in scores:
        if not s.skipped and not s.error:
            means.setdefault(s.metric, []).append(s.value)
    return {
        "run_id": str(run_id),
        "app": run.app,
        "git_sha": run.git_sha,
        "mode": run.mode,
        "metrics": {k: round(sum(v) / len(v), 3) for k, v in means.items()},
        "n_scores": len(scores),
        "worst_examples": [
            {
                "trace_id": s.trace_id,
                "metric": s.metric,
                "value": round(s.value, 3),
                "rationale": _clip(s.rationale, 200),
            }
            for s in sorted(
                (s for s in scores if not s.skipped and not s.error), key=lambda s: s.value
            )[:5]
        ],
    }


def _redteam_context(engine: Engine, run_id: UUID | None, app: str | None) -> dict[str, Any]:
    with Session(engine) as session:
        if run_id:
            run = session.get(RedteamRun, run_id)
            runs = [run] if run else []
        else:
            q = select(RedteamRun)
            if app:
                q = q.where(RedteamRun.app == app)
            runs = list(session.exec(q.order_by(RedteamRun.started_at.desc()).limit(5)).all())  # type: ignore[attr-defined]
    return {
        "runs": [
            {
                "run_id": str(r.id),
                "app": r.app,
                "git_sha": r.git_sha,
                "defence": r.defence,
                "asr": round(r.asr, 3),
                "successes": r.successes,
                "total": r.total_probes,
                "detector_caught": r.detector_caught,
            }
            for r in runs
            if r
        ]
    }


async def _overview_context(store: SpanStore, engine: Engine, app: str | None) -> dict[str, Any]:
    import time

    now = time.time_ns()
    stats = await store.overview(
        app=app, since_ns=now - 24 * 3600 * 10**9, until_ns=now, bucket_ns=3600 * 10**9
    )
    with Session(engine) as session:
        recent_runs = session.exec(
            select(EvalRun).order_by(EvalRun.started_at.desc()).limit(3)
        ).all()  # type: ignore[attr-defined]
    return {
        "window": "24h",
        "app": app or "all apps",
        "traces": stats.traces,
        "errors": stats.errors,
        "error_rate": round(stats.error_rate, 4),
        "p95_ms": round(stats.p95_ms, 1),
        "tokens": stats.tokens_in + stats.tokens_out,
        "top_models": [{"model": m.model, "calls": m.calls} for m in stats.by_model[:5]],
        "apps": [{"app": a.app, "traces": a.traces, "errors": a.errors} for a in stats.by_app[:8]],
        "recent_eval_runs": [
            {"run_id": str(r.id), "app": r.app, "git_sha": r.git_sha} for r in recent_runs
        ],
    }


async def build_context(req: ChatRequest, store: SpanStore, engine: Engine) -> dict[str, Any]:
    if req.focus == "trace" and req.trace_id:
        return await _trace_context(store, engine, req.trace_id)
    if req.focus == "eval_run" and req.run_id:
        return _eval_context(engine, req.run_id)
    if req.focus == "redteam_run":
        return _redteam_context(engine, req.run_id, req.app)
    return await _overview_context(store, engine, req.app)


def _suggestions(focus: Focus, context: dict[str, Any]) -> list[str]:
    if focus == "trace":
        out = ["Why did this trace get its faithfulness score?", "Show similar failing traces"]
        if context.get("flagged_spans"):
            out.insert(0, "Explain the injection flagged in this trace")
        return out
    if focus == "eval_run":
        return ["Which examples regressed the most?", "How does this run compare to the baseline?"]
    if focus == "redteam_run":
        return ["Which attack category has the highest ASR?", "Did the defence reduce ASR?"]
    return [
        "What is driving my error rate in the last 24h?",
        "Which model costs the most tokens?",
        "Summarise the latest red-team run",
    ]


def _fallback_answer(req: ChatRequest, context: dict[str, Any]) -> str:
    """Deterministic summary when no LLM key is configured (never fabricates)."""
    if "error" in context:
        return f"I couldn't load that: {context['error']}."
    lines = [
        "No frontier judge is configured (set ANTHROPIC_API_KEY), so here is the raw Lens data for your question:",
        "",
    ]
    for k, v in context.items():
        rendered = json.dumps(v, ensure_ascii=False) if isinstance(v, list | dict) else str(v)
        lines.append(f"- {k}: {_clip(rendered, 300)}")
    lines.append("")
    lines.append(
        "Set an Anthropic API key on the API to get natural-language answers grounded in this data."
    )
    return "\n".join(lines)


async def chat(
    req: ChatRequest, store: SpanStore, engine: Engine, settings: Settings
) -> ChatResponse:
    context = await build_context(req, store, engine)
    suggestions = _suggestions(req.focus, context)

    router = JudgeRouter.from_env()
    try:
        judge = router.get("frontier")
    except KeyError:
        judge = None

    # No usable judge (no cassette, no API key) → deterministic fallback.
    import os

    has_key = bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("LENS_JUDGE_CASSETTE")
    )
    if judge is None or not has_key:
        return ChatResponse(
            answer=_fallback_answer(req, context),
            grounded=False,
            context_summary=context,
            suggestions=suggestions,
        )

    history = "\n".join(f"{m.role.upper()}: {m.content}" for m in req.messages[-6:])
    user_prompt = (
        f"Lens data (focus: {req.focus}):\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```\n\n"
        f"Conversation so far:\n{history}\n\n"
        "Answer the latest user message using only the Lens data above."
    )
    try:
        resp = await judge._complete(SYSTEM, user_prompt, temperature=0.2, max_tokens=800)
    except Exception as exc:  # noqa: BLE001
        log.warning("assistant LLM call failed: %s", exc)
        return ChatResponse(
            answer=_fallback_answer(req, context),
            grounded=False,
            context_summary=context,
            suggestions=suggestions,
        )
    return ChatResponse(
        answer=resp.text.strip(),
        grounded=True,
        model=resp.model,
        context_summary=context,
        cost_usd=resp.cost_usd,
        suggestions=suggestions,
    )
