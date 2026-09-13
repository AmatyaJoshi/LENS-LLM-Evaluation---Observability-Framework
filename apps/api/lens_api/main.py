"""Lens API entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lens_api import ws
from lens_api.db import engine_for
from lens_api.ingest import otlp_http
from lens_api.models.clickhouse import make_store
from lens_api.routers import assistant, ci, datasets, evals, judges, labels, redteam, traces
from lens_api.settings import Settings, get_settings
from lens_core import __version__

log = logging.getLogger("lens.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.store = make_store(settings)
        app.state.db_engine = engine_for(settings.postgres_dsn)
        log.info(
            "span store ready (%s); db %s",
            settings.span_store,
            settings.postgres_dsn.split("@")[-1],
        )
        yield

    app = FastAPI(
        title="Lens API",
        version=__version__,
        description="LLM evaluation & observability: OTLP ingest, trajectories, scores, red team.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.env != "prod" else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        store = getattr(app.state, "store", None)
        ok = await store.ping() if store is not None else False
        return {
            "status": "ok" if ok else "degraded",
            "version": __version__,
            "span_store": settings.span_store,
            "ws_clients": ws.hub.client_count,
            "eval_dispatch": settings.eval_dispatch,
        }

    app.include_router(otlp_http.router)
    app.include_router(ws.router)
    app.include_router(traces.router)
    app.include_router(datasets.router)
    app.include_router(evals.router)
    app.include_router(labels.router)
    app.include_router(judges.router)
    app.include_router(redteam.router)
    app.include_router(assistant.router)
    app.include_router(ci.router)
    return app


app = create_app()
