"""Normalised trace model (SPEC.md §3.1 — contract).

Every ingested span, regardless of the semantic convention it arrived in, is
normalised into these types. ``Span`` preserves the raw attributes verbatim;
``LLMCall``/``ToolCall``/``Retrieval`` are *derived* views keyed by ``span_id``;
``Trajectory`` is the ordered agent run assembled from them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SpanKind = Literal["llm", "tool", "retrieval", "agent_step", "chain", "embedding", "other"]
SpanStatus = Literal["ok", "error"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SpanEvent(_Frozen):
    name: str
    time_ns: int
    attributes: dict[str, Any] = Field(default_factory=dict)


class Span(BaseModel):
    """One OTel span after kind detection. ``attributes`` are never dropped."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: SpanKind
    start_ns: int
    end_ns: int
    status: SpanStatus = "ok"
    status_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    resource: dict[str, Any] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)
    truncated_attributes: list[str] = Field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1_000_000


class ToolCallRequest(_Frozen):
    """A tool call *requested* by the model inside an assistant message."""

    id: str | None = None
    name: str
    arguments: dict[str, Any] | str | None = None


class Message(_Frozen):
    role: str
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)


class LLMCall(_Frozen):
    span_id: str
    provider: str
    model: str
    messages_in: list[Message] = Field(default_factory=list)
    message_out: Message | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = None
    temperature: float | None = None
    prompt_version: str | None = None
    finish_reason: str | None = None
    error: str | None = None
    duration_ms: float = 0.0


class RetrievedDoc(_Frozen):
    text: str
    id: str | None = None
    score: float | None = None
    rank: int


class Retrieval(_Frozen):
    span_id: str
    query: str
    documents: list[RetrievedDoc] = Field(default_factory=list)
    duration_ms: float = 0.0


class ToolCall(_Frozen):
    """A tool *execution* span (as opposed to a ``ToolCallRequest`` in a message)."""

    span_id: str
    name: str
    call_id: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0


class Step(_Frozen):
    """One agent step: at most one LLM call plus the tool calls / retrievals around it."""

    index: int
    name: str
    span_id: str | None = None
    llm_call: LLMCall | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    retrievals: list[Retrieval] = Field(default_factory=list)
    start_ns: int
    end_ns: int


class Trajectory(_Frozen):
    trace_id: str
    app: str
    run_id: str | None = None
    steps: list[Step] = Field(default_factory=list)
    final_output: str | None = None
    user_input: str | None = None
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    duration_ms: float = 0.0
    status: SpanStatus = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def llm_calls(self) -> list[LLMCall]:
        return [s.llm_call for s in self.steps if s.llm_call is not None]

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [t for s in self.steps for t in s.tool_calls]

    @property
    def retrievals(self) -> list[Retrieval]:
        return [r for s in self.steps for r in s.retrievals]
