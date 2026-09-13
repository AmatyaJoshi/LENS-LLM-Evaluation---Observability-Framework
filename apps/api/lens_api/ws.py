"""WebSocket hub: pushes ``{"type": "trace", ...}`` summaries as traces are ingested."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


class TraceHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)


hub = TraceHub()
router = APIRouter()


@router.websocket("/ws/traces")
async def traces_ws(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            # Clients may send pings; we ignore payloads and only push.
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws)
