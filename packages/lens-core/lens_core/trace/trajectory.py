"""Trajectory reconstruction (SPEC.md §1.1 goal 2, §3.1).

Input: the normalised ``Span`` list for one trace plus the derived
``LLMCall``/``ToolCall``/``Retrieval`` views (keyed by ``span_id``), produced by
the ingest normaliser. Output: an ordered ``Trajectory``.

Algorithm
---------
1. Spans are sorted by ``start_ns`` (ties broken by ``span_id``) and a parent map
   is built.
2. Every derived item is assigned to its *nearest* ``agent_step`` ancestor
   (``None`` when the trace has no agent spans, or the item sits outside them).
   Agent spans with no derived descendants still yield an (empty) step so that
   routing/decision nodes remain visible.
3. Inside each agent group items are split into steps with one rule:
   **an LLM call opens a new step if the current step already has one.**
   Retrievals that precede an LLM call and tool executions that follow it
   therefore land in the same step as that call, which is the natural
   "think, then act" unit of an agent loop.
4. Tool executions without an explicit call id are linked to the earliest
   unmatched ``ToolCallRequest`` of the same name emitted by a previous LLM call
   in the trace (many instrumentations do not propagate the id).
5. ``user_input`` is the first ``user`` message of the first LLM call;
   ``final_output`` is the content of the last LLM call that produced any.
   Both fall back to the root span's ``traceloop.entity.input/output``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from lens_core.trace.model import (
    LLMCall,
    Retrieval,
    Span,
    Step,
    ToolCall,
    Trajectory,
)

# Attribute names that flow into Trajectory.run_id / metadata (SPEC.md §4, Lens namespace).
LENS_RUN_ID = "lens.run.id"
LENS_METADATA_ATTRS: tuple[str, ...] = (
    "lens.session.id",
    "lens.user.feedback",
    "lens.eval.expected_output",
    "lens.prompt.version",
)
METADATA_PREFIXES: tuple[str, ...] = ("sentinel.",)
SERVICE_NAME = "service.name"
TRACELOOP_ENTITY_INPUT = "traceloop.entity.input"
TRACELOOP_ENTITY_OUTPUT = "traceloop.entity.output"
# Logical step/agent name: instrumentations decorate span names ("x.workflow"), the entity
# name is the stable label (SPEC.md §4 agent-step row).
STEP_NAME_ATTRS: tuple[str, ...] = ("gen_ai.agent.name", "traceloop.entity.name")


def step_name(span: Span) -> str:
    for key in STEP_NAME_ATTRS:
        value = span.attributes.get(key)
        if value:
            return str(value)
    return span.name


class DerivedSpans(BaseModel):
    """Derived views keyed by span_id (produced by the ingest normaliser)."""

    llm_calls: dict[str, LLMCall] = Field(default_factory=dict)
    tool_calls: dict[str, ToolCall] = Field(default_factory=dict)
    retrievals: dict[str, Retrieval] = Field(default_factory=dict)


_Item = LLMCall | ToolCall | Retrieval


def _sorted(spans: Iterable[Span]) -> list[Span]:
    return sorted(spans, key=lambda s: (s.start_ns, s.span_id))


def _nearest_agent(span: Span, by_id: dict[str, Span]) -> Span | None:
    cur = span.parent_span_id
    seen: set[str] = set()
    while cur is not None and cur in by_id and cur not in seen:
        seen.add(cur)
        parent = by_id[cur]
        if parent.kind == "agent_step":
            return parent
        cur = parent.parent_span_id
    return None


def _split_into_steps(
    items: Sequence[tuple[Span, _Item]],
    *,
    agent: Span | None,
    start_index: int,
) -> list[Step]:
    """Apply the one-LLM-call-per-step rule to an ordered list of derived items."""
    name = step_name(agent) if agent is not None else "step"
    agent_id = agent.span_id if agent is not None else None

    buckets: list[list[tuple[Span, _Item]]] = [[]]
    for span, item in items:
        current = buckets[-1]
        if isinstance(item, LLMCall) and any(isinstance(i, LLMCall) for _, i in current):
            buckets.append([])
            current = buckets[-1]
        current.append((span, item))

    non_empty = [b for b in buckets if b]
    if not non_empty and agent is not None:
        # Agent span with no derived descendants: keep it as an empty step.
        return [
            Step(
                index=start_index,
                name=name,
                span_id=agent_id,
                start_ns=agent.start_ns,
                end_ns=agent.end_ns,
            )
        ]

    steps: list[Step] = []
    for offset, bucket in enumerate(non_empty):
        llm = next((i for _, i in bucket if isinstance(i, LLMCall)), None)
        tools = [i for _, i in bucket if isinstance(i, ToolCall)]
        rets = [i for _, i in bucket if isinstance(i, Retrieval)]
        if agent is not None and len(non_empty) == 1:
            start_ns, end_ns = agent.start_ns, agent.end_ns
        else:
            start_ns = min(s.start_ns for s, _ in bucket)
            end_ns = max(s.end_ns for s, _ in bucket)
        steps.append(
            Step(
                index=start_index + offset,
                name=name,
                span_id=agent_id,
                llm_call=llm,
                tool_calls=tools,
                retrievals=rets,
                start_ns=start_ns,
                end_ns=end_ns,
            )
        )
    return steps


def _link_tool_call_ids(
    ordered: Sequence[tuple[Span, _Item]], derived: DerivedSpans
) -> dict[str, ToolCall]:
    """Fill missing ``ToolCall.call_id`` from earlier LLM ``ToolCallRequest``s by name."""
    pending: dict[str, list[str]] = defaultdict(list)  # tool name -> unmatched request ids
    used: set[str] = set()
    for _, item in ordered:
        if isinstance(item, ToolCall) and item.call_id is not None:
            used.add(item.call_id)
    linked: dict[str, ToolCall] = dict(derived.tool_calls)
    for _, item in ordered:
        if isinstance(item, LLMCall):
            for req in item.tool_calls:
                if req.id is not None and req.id not in used:
                    pending[req.name].append(req.id)
        elif isinstance(item, ToolCall) and item.call_id is None and pending.get(item.name):
            call_id = pending[item.name].pop(0)
            linked[item.span_id] = item.model_copy(update={"call_id": call_id})
    return linked


def _first_attr(spans: Sequence[Span], key: str) -> Any | None:
    for s in spans:
        if key in s.attributes:
            return s.attributes[key]
    return None


def _entity_text(value: Any) -> str | None:
    """Render ``traceloop.entity.input/output`` into a plain string when possible."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return value
        if isinstance(parsed, str):
            return parsed
        return _entity_text(parsed)
    if isinstance(value, dict):
        kwargs = value.get("kwargs")
        args = value.get("args")
        if isinstance(kwargs, dict) and len(kwargs) == 1:
            return _entity_text(next(iter(kwargs.values())))
        if isinstance(args, list) and len(args) == 1 and not kwargs:
            return _entity_text(args[0])
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def build_trajectory(
    spans: Iterable[Span],
    derived: DerivedSpans,
    *,
    app: str | None = None,
) -> Trajectory:
    ordered_spans = _sorted(spans)
    if not ordered_spans:
        raise ValueError("cannot build a trajectory from zero spans")

    by_id = {s.span_id: s for s in ordered_spans}
    trace_id = ordered_spans[0].trace_id
    roots = [s for s in ordered_spans if s.parent_span_id is None or s.parent_span_id not in by_id]
    root = roots[0]

    resolved_app = app or str(root.resource.get(SERVICE_NAME) or "unknown")

    # --- collect derived items in span order ------------------------------------------------
    ordered_items: list[tuple[Span, _Item]] = []
    for s in ordered_spans:
        item: _Item | None = (
            derived.llm_calls.get(s.span_id)
            or derived.tool_calls.get(s.span_id)
            or derived.retrievals.get(s.span_id)
        )
        if item is not None:
            ordered_items.append((s, item))

    linked_tools = _link_tool_call_ids(ordered_items, derived)
    ordered_items = [
        (s, linked_tools[s.span_id] if isinstance(i, ToolCall) else i) for s, i in ordered_items
    ]

    # --- group by nearest agent ancestor ----------------------------------------------------
    groups: dict[str | None, list[tuple[Span, _Item]]] = {}
    group_order: list[tuple[int, str, str | None]] = []
    for s in ordered_spans:
        if s.kind == "agent_step":
            groups.setdefault(s.span_id, [])
            group_order.append((s.start_ns, s.span_id, s.span_id))
    for s, item in ordered_items:
        agent = _nearest_agent(s, by_id)
        key = agent.span_id if agent is not None else None
        if key not in groups:
            groups[key] = []
            group_order.append((s.start_ns, s.span_id, None))
        groups[key].append((s, item))
    group_order.sort()

    steps: list[Step] = []
    for _, _, key in group_order:
        agent = by_id[key] if key is not None else None
        steps.extend(_split_into_steps(groups[key], agent=agent, start_index=len(steps)))

    # --- scalar fields ----------------------------------------------------------------------
    llm_calls = [s.llm_call for s in steps if s.llm_call is not None]

    user_input: str | None = None
    for call in llm_calls:
        user_msgs = [m for m in call.messages_in if m.role == "user" and m.content]
        if user_msgs:
            user_input = user_msgs[0].content
            break
    if user_input is None:
        user_input = _entity_text(root.attributes.get(TRACELOOP_ENTITY_INPUT))

    final_output: str | None = None
    for call in reversed(llm_calls):
        if call.message_out is not None and call.message_out.content:
            final_output = call.message_out.content
            break
    if final_output is None:
        final_output = _entity_text(root.attributes.get(TRACELOOP_ENTITY_OUTPUT))

    total_tokens = sum(c.tokens_in + c.tokens_out for c in llm_calls)
    total_cost = sum(c.cost_usd or 0.0 for c in llm_calls)
    start_ns = min(s.start_ns for s in ordered_spans)
    end_ns = max(s.end_ns for s in ordered_spans)

    metadata: dict[str, Any] = {}
    for key in LENS_METADATA_ATTRS:
        value = _first_attr(ordered_spans, key)
        if value is not None:
            metadata[key] = value
    for s in ordered_spans:
        for k, v in s.attributes.items():
            if k.startswith(METADATA_PREFIXES) and k not in metadata:
                metadata[k] = v
    metadata["root_span"] = step_name(root)
    metadata["span_count"] = len(ordered_spans)

    run_id_raw = _first_attr(ordered_spans, LENS_RUN_ID)
    run_id = str(run_id_raw) if run_id_raw is not None else None

    status = "error" if any(s.status == "error" for s in ordered_spans) else "ok"

    return Trajectory(
        trace_id=trace_id,
        app=resolved_app,
        run_id=run_id,
        steps=steps,
        final_output=final_output,
        user_input=user_input,
        total_cost_usd=round(total_cost, 8),
        total_tokens=total_tokens,
        duration_ms=(end_ns - start_ns) / 1_000_000,
        status=status,
        metadata=metadata,
    )
