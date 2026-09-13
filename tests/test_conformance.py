"""SPEC.md §4 conformance suite: four instrumentation families, one logical run, one Trajectory."""

from __future__ import annotations

import pytest

from lens_api.ingest import normalize
from lens_core.trace import Trajectory, build_trajectory
from tests.conftest import FIXTURE_NAMES, load_fixture


def trajectory_of(name: str) -> Trajectory:
    spans = normalize.otlp_json_to_spans(load_fixture(name))
    return build_trajectory(spans, normalize.derive(spans))


@pytest.fixture(scope="module")
def trajectories() -> dict[str, Trajectory]:
    return {name: trajectory_of(name) for name in FIXTURE_NAMES}


@pytest.mark.parametrize("name", FIXTURE_NAMES[1:])
def test_all_families_normalise_identically(trajectories: dict[str, Trajectory], name: str) -> None:
    reference = trajectories[FIXTURE_NAMES[0]]
    other = trajectories[name]
    assert other.model_dump() == reference.model_dump(), f"{name} differs from {FIXTURE_NAMES[0]}"


def test_reference_trajectory_content(trajectories: dict[str, Trajectory]) -> None:
    t = trajectories["openllmetry_python"]
    assert t.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert t.app == "rag_demo"
    assert t.run_id == "run-7"
    assert t.status == "ok"
    assert t.duration_ms == 2000.0
    assert t.total_tokens == 182 + 21 + 231 + 16
    assert t.total_cost_usd == 0.0
    assert t.user_input is not None and t.user_input.endswith(
        "Question: What is the refund window for Acme Pro?"
    )
    assert t.final_output == "Acme Pro purchases can be refunded within 30 days of purchase."
    assert t.metadata["lens.session.id"] == "sess-001"
    assert t.metadata["root_span"] == "rag_pipeline"
    assert t.metadata["span_count"] == 5

    assert [s.name for s in t.steps] == ["rag_pipeline", "rag_pipeline"]
    s0, s1 = t.steps

    assert len(s0.retrievals) == 1
    ret = s0.retrievals[0]
    assert ret.query == "What is the refund window for Acme Pro?"
    assert [d.id for d in ret.documents] == ["doc-17", "doc-42"]
    assert [d.rank for d in ret.documents] == [1, 2]
    assert ret.documents[0].score == 0.91

    assert s0.llm_call is not None
    assert (s0.llm_call.provider, s0.llm_call.model) == ("openai", "gpt-4o-mini")
    assert [m.role for m in s0.llm_call.messages_in] == ["system", "user"]
    assert s0.llm_call.message_out is not None
    assert s0.llm_call.message_out.content is None
    assert s0.llm_call.finish_reason == "tool_calls"
    assert len(s0.llm_call.tool_calls) == 1
    req = s0.llm_call.tool_calls[0]
    assert (req.id, req.name, req.arguments) == ("call_1", "lookup_policy", {"product": "Acme Pro"})

    assert len(s0.tool_calls) == 1
    tool = s0.tool_calls[0]
    assert tool.name == "lookup_policy"
    assert tool.call_id == "call_1"
    assert tool.args == {"product": "Acme Pro"}
    assert tool.result == {"refund_days": 30}
    assert tool.duration_ms == 50.0

    assert s1.llm_call is not None
    assert [m.role for m in s1.llm_call.messages_in] == ["system", "user", "assistant", "tool"]
    tool_msg = s1.llm_call.messages_in[3]
    assert tool_msg.tool_call_id == "call_1"
    assert tool_msg.content == '{"refund_days": 30}'
    assert s1.llm_call.messages_in[2].tool_calls == [req]
    assert s1.llm_call.finish_reason == "stop"
    assert s1.tool_calls == [] and s1.retrievals == []


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_span_kinds_detected(name: str) -> None:
    spans = normalize.otlp_json_to_spans(load_fixture(name))
    kinds = {s.span_id: s.kind for s in spans}
    assert kinds == {
        "b7ad6b7169203331": "agent_step",
        "1111111111111111": "retrieval",
        "2222222222222222": "llm",
        "3333333333333333": "tool",
        "4444444444444444": "llm",
    }


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_raw_attributes_are_preserved(name: str) -> None:
    payload = load_fixture(name)
    raw_counts = {
        s["spanId"]: len(s["attributes"])
        for rs in payload["resourceSpans"]
        for ss in rs["scopeSpans"]
        for s in ss["spans"]
    }
    for span in normalize.otlp_json_to_spans(payload):
        # +1 for the otel.scope.name we add; nothing is ever dropped.
        assert len(span.attributes) == raw_counts[span.span_id] + 1
        assert span.resource["service.name"] == "rag_demo"
