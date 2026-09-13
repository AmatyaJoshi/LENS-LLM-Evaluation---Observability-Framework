"""Factory for routers whose implementation lands in a later phase (SPEC.md §10)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status


def stub_router(name: str, phase: int) -> APIRouter:
    router = APIRouter(prefix=f"/{name}", tags=[name])

    @router.get("")
    async def _list() -> list[Any]:
        return []

    @router.post("")
    async def _create() -> None:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"/{name} is scheduled for phase {phase} (SPEC.md §10)",
        )

    return router
