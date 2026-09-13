"""FastAPI dependencies: span store, API-key auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from lens_api.models.clickhouse import SpanStore
from lens_api.settings import Settings, get_settings


def get_store(request: Request) -> SpanStore:
    store: SpanStore | None = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "span store not ready")
    return store


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_lens_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.api_key:
        return
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None
    if x_lens_api_key == settings.api_key or bearer == settings.api_key:
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")
