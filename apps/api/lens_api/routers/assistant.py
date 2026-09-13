"""AI Assistant API: a Lens-data-grounded copilot (SPEC.md observability goals).

``POST /assistant/chat`` answers a question from the operator's own traces, eval
runs and red-team results. It never fabricates: with no LLM key it returns the
raw context bundle instead.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from lens_api.deps import get_store, require_api_key
from lens_api.models.clickhouse import SpanStore
from lens_api.services import assistant as svc
from lens_api.services.assistant import ChatRequest, ChatResponse
from lens_api.settings import Settings, get_settings

router = APIRouter(prefix="/assistant", tags=["assistant"], dependencies=[Depends(require_api_key)])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    store: Annotated[SpanStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResponse:
    return await svc.chat(body, store, request.app.state.db_engine, settings)


@router.get("/capabilities")
async def capabilities(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    from lens_core.judges.router import llm_available

    grounded = llm_available()
    return {
        "grounded_answers": grounded,
        "focuses": ["overview", "trace", "eval_run", "redteam_run"],
        "note": ""
        if grounded
        else "Set ANTHROPIC_API_KEY on the API for natural-language answers.",
    }
