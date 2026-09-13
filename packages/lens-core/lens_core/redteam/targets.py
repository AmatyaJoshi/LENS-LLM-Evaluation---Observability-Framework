"""Target adapters (SPEC.md §6.1).

A ``Target`` receives the probe messages (plus optional injected content for
indirect attacks) and returns a ``TargetResponse`` capturing what the app said
and did: its text output, the tools it called, and an optional trace id so the
red-team result can be linked to the ingested trajectory.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from lens_core.redteam.probes import Message, Probe


class ToolInvocation(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class TargetResponse(BaseModel):
    output: str = ""
    tools_called: list[ToolInvocation] = Field(default_factory=list)
    trace_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Target(Protocol):
    name: str

    async def send(self, probe: Probe, messages: list[Message]) -> TargetResponse: ...


class HttpTarget:
    """POSTs ``{messages, probe_id, inject_into}`` to an HTTP endpoint.

    The endpoint should return ``{output, tools_called?, trace_id?}``. This is the
    adapter used for the RAG demo and any app exposing a chat endpoint.
    """

    def __init__(
        self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 120.0
    ) -> None:
        self.url = url
        self.name = url
        self._headers = headers or {}
        self._timeout = timeout

    async def send(self, probe: Probe, messages: list[Message]) -> TargetResponse:
        body = {
            "messages": [m.model_dump() for m in messages],
            "probe_id": probe.id,
            "inject_into": probe.inject_into,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(self.url, json=body, headers=self._headers)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as exc:
            return TargetResponse(error=f"{type(exc).__name__}: {exc}")
        tools = [ToolInvocation.model_validate(t) for t in data.get("tools_called", [])]
        return TargetResponse(
            output=str(data.get("output", "")),
            tools_called=tools,
            trace_id=data.get("trace_id"),
            raw=data,
        )


class CallableTarget:
    """Wraps an in-process async callable ``(messages) -> TargetResponse | dict | str``.

    Used for the Python-entrypoint and LangGraph adapters, and for tests.
    """

    def __init__(
        self,
        fn: Callable[[list[Message], Probe], Awaitable[TargetResponse | dict[str, Any] | str]],
        *,
        name: str = "callable",
    ) -> None:
        self._fn = fn
        self.name = name

    async def send(self, probe: Probe, messages: list[Message]) -> TargetResponse:
        result = await self._fn(messages, probe)
        if isinstance(result, TargetResponse):
            return result
        if isinstance(result, str):
            return TargetResponse(output=result)
        return TargetResponse.model_validate(result)
