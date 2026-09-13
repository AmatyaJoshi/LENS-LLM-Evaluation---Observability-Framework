from typing import Any

from lens_core.trace import (
    LLMCall,
    Message,
    Retrieval,
    RetrievedDoc,
    Span,
    ToolCall,
    ToolCallRequest,
    build_trajectory,
)
from lens_core.trace.trajectory import DerivedSpans

T = "0" * 32


def _span(
    sid: str, kind: str, start: int, end: int, parent: str | None = None, **attrs: Any
) -> Span:
    return Span(
        trace_id=T,
        span_id=sid,
        parent_span_id=parent,
        name=str(attrs.pop("name", sid)),
        kind=kind,  # type: ignore[arg-type]
        start_ns=start,
        end_ns=end,
        attributes=attrs,
        resource={"service.name": "unit"},
    )


def test_llm_call_opens_new_step_and_tools_follow_their_call() -> None:
    spans = [
        _span("root", "agent_step", 0, 100, name="agent"),
        _span("r1", "retrieval", 1, 5, "root"),
        _span("l1", "llm", 6, 20, "root"),
        _span("t1", "tool", 21, 30, "root"),
        _span("l2", "llm", 31, 90, "root"),
    ]
    req = ToolCallRequest(id="c1", name="lookup", arguments={})
    derived = DerivedSpans(
        llm_calls={
            "l1": LLMCall(
                span_id="l1",
                provider="openai",
                model="m",
                messages_in=[Message(role="user", content="q?")],
                message_out=Message(role="assistant", tool_calls=[req]),
                tool_calls=[req],
                tokens_in=10,
                tokens_out=2,
            ),
            "l2": LLMCall(
                span_id="l2",
                provider="openai",
                model="m",
                message_out=Message(role="assistant", content="final"),
                tokens_in=20,
                tokens_out=3,
            ),
        },
        tool_calls={"t1": ToolCall(span_id="t1", name="lookup")},
        retrievals={
            "r1": Retrieval(span_id="r1", query="q?", documents=[RetrievedDoc(text="d", rank=1)])
        },
    )
    traj = build_trajectory(spans, derived)
    assert traj.app == "unit"
    assert [len(s.retrievals) for s in traj.steps] == [1, 0]
    assert [len(s.tool_calls) for s in traj.steps] == [1, 0]
    assert traj.steps[0].llm_call is not None and traj.steps[0].llm_call.span_id == "l1"
    assert traj.steps[1].llm_call is not None and traj.steps[1].llm_call.span_id == "l2"
    assert traj.steps[0].tool_calls[0].call_id == "c1", "missing call id linked by name"
    assert traj.user_input == "q?"
    assert traj.final_output == "final"
    assert traj.total_tokens == 35
    assert traj.duration_ms == 100 / 1e6
    assert all(s.name == "agent" for s in traj.steps)


def test_agent_span_without_children_is_an_empty_step() -> None:
    spans = [
        _span("root", "agent_step", 0, 100, name="graph"),
        _span("route", "agent_step", 1, 2, "root", name="route"),
        _span("l1", "llm", 3, 50, "root"),
    ]
    derived = DerivedSpans(llm_calls={"l1": LLMCall(span_id="l1", provider="x", model="y")})
    traj = build_trajectory(spans, derived)
    assert [s.name for s in traj.steps] == ["graph", "route"]
    assert traj.steps[1].llm_call is None and traj.steps[1].span_id == "route"


def test_no_agent_spans_falls_back_to_flat_steps_and_entity_io() -> None:
    attrs = {
        "traceloop.entity.input": '{"args": [], "kwargs": {"q": "hello"}}',
        "traceloop.entity.output": '"world"',
    }
    spans = [_span("root", "chain", 0, 10, name="pipeline", **attrs)]
    traj = build_trajectory(spans, DerivedSpans())
    assert traj.steps == []
    assert traj.user_input == "hello"
    assert traj.final_output == "world"
