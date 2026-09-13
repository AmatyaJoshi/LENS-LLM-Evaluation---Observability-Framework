"""Metric unit tests with cassette judges: no live LLM is ever called."""

from __future__ import annotations

import pytest

from lens_core.judges.cassette import CassetteJudge
from lens_core.metrics import Engine, EvalItem, ExpectedTool, get_metric, list_metrics
from lens_core.metrics.context_precision import rank_weighted_precision
from lens_core.metrics.trajectory import detect_loop
from lens_core.trace.model import (
    LLMCall,
    Message,
    Retrieval,
    RetrievedDoc,
    Step,
    ToolCall,
    Trajectory,
)

Q = "What is the refund window for Acme Pro?"
CTX = [
    "Acme Pro purchases can be refunded within 30 days of purchase.",
    "Acme Basic has a 14-day refund window.",
]
GOOD = "Acme Pro purchases can be refunded within 30 days of purchase."
BAD = "Acme Pro can be refunded within 60 days, and refunds are handled by the finance team."


def test_registry_has_all_spec_metrics() -> None:
    names = set(list_metrics())
    assert {
        "faithfulness",
        "answer_relevance",
        "context_precision",
        "context_recall",
        "hallucination",
        "tool_correctness",
        "trajectory_efficiency",
        "task_completion",
        "safety",
        "calibration",
    } <= names


async def test_faithfulness_counts_supported_claims() -> None:
    judge = (
        CassetteJudge()
        .script(
            "claim_extraction",
            {
                "claims": [
                    "Acme Pro can be refunded within 60 days.",
                    "Refunds are handled by the finance team.",
                ]
            },
        )
        .script(
            "claim_verification",
            {
                "verdicts": [
                    {
                        "claim": "Acme Pro can be refunded within 60 days.",
                        "verdict": "contradicted",
                        "evidence": "30 days",
                    },
                    {
                        "claim": "Refunds are handled by the finance team.",
                        "verdict": "unverifiable",
                        "evidence": None,
                    },
                ]
            },
        )
    )
    r = await get_metric("faithfulness").score(EvalItem(input=Q, output=BAD, contexts=CTX), judge)
    assert r.value == 0.0
    assert r.sub_scores["contradicted_rate"] == 0.5 and r.sub_scores["unverifiable_rate"] == 0.5
    assert len(r.details["unsupported"]) == 2
    assert r.judge_prompt_version == "claim_extraction@1;claim_verification@1"
    assert r.judge_model == "cassette" and r.latency_ms >= 0


async def test_faithfulness_vacuous_when_no_claims() -> None:
    judge = CassetteJudge().script("claim_extraction", {"claims": []})
    r = await get_metric("faithfulness").score(
        EvalItem(input=Q, output="Happy to help!", contexts=CTX), judge
    )
    assert r.value == 1.0 and "no factual claims" in r.rationale


async def test_hallucination_weights_unverifiable_half() -> None:
    judge = (
        CassetteJudge()
        .script("claim_extraction", {"claims": ["a", "b"]})
        .script(
            "claim_verification",
            {
                "verdicts": [
                    {"claim": "a", "verdict": "contradicted"},
                    {"claim": "b", "verdict": "unverifiable"},
                ]
            },
        )
    )
    r = await get_metric("hallucination").score(EvalItem(input=Q, output=BAD, contexts=CTX), judge)
    assert r.value == pytest.approx(0.75)


async def test_hallucination_falls_back_to_world_knowledge_without_contexts() -> None:
    judge = (
        CassetteJudge()
        .script("claim_extraction", {"claims": ["Paris is the capital of France."]})
        .script(
            "hallucination_world",
            {"verdicts": [{"claim": "Paris is the capital of France.", "verdict": "supported"}]},
        )
    )
    r = await get_metric("hallucination").score(
        EvalItem(input="capital?", output="Paris is the capital of France."), judge
    )
    assert r.value == 0.0 and r.details["basis"].startswith("world knowledge")


async def test_skipped_when_requirements_missing() -> None:
    r = await get_metric("faithfulness").score(EvalItem(input=Q, output=GOOD), CassetteJudge())
    assert r.skipped and "contexts" in r.rationale


async def test_relevance_blends_embeddings_and_rubric() -> None:
    judge = (
        CassetteJudge(embeddings={Q: [1.0, 0.0], "q1": [1.0, 0.0], "q2": [0.0, 1.0]})
        .script("question_generation", {"questions": ["q1", "q2"]})
        .script("relevance_rubric", {"score": 5, "rationale": "direct"})
    )
    r = await get_metric("answer_relevance").score(EvalItem(input=Q, output=GOOD), judge)
    assert r.sub_scores["embedding_similarity"] == pytest.approx(0.5)
    assert r.sub_scores["rubric"] == 1.0
    assert r.value == pytest.approx(0.75)


async def test_relevance_rubric_only_without_embeddings() -> None:
    judge = (
        CassetteJudge()
        .script("question_generation", {"questions": ["q1"]})
        .script("relevance_rubric", {"score": 3, "rationale": "partial"})
    )
    r = await get_metric("answer_relevance").score(EvalItem(input=Q, output=GOOD), judge)
    assert r.value == 0.5 and "embedding_similarity" not in r.sub_scores


def test_rank_weighted_precision_formula() -> None:
    assert rank_weighted_precision([True, False]) == 1.0
    assert rank_weighted_precision([False, True]) == 0.5
    assert rank_weighted_precision([True, True, False]) == 1.0
    assert rank_weighted_precision([False, False]) == 0.0


async def test_context_precision_and_recall() -> None:
    judge = (
        CassetteJudge()
        .script("context_usefulness", {"answers": [{"answer": "no"}, {"answer": "yes"}]})
        .script("attribution", {"answers": [{"answer": "yes"}, {"answer": "no"}]})
    )
    item = EvalItem(
        input=Q,
        output=GOOD,
        contexts=CTX,
        expected_output="Acme Pro: 30 days. Refunds hit the card in 5 days.",
    )
    p = await get_metric("context_precision").score(item, judge)
    assert p.value == 0.5
    rc = await get_metric("context_recall").score(item, judge)
    assert rc.value == 0.5 and len(rc.details["missing"]) == 1


async def test_task_completion_swaps_pairwise_order() -> None:
    judge = (
        CassetteJudge()
        .script("task_completion", {"score": 5, "rationale": "ok"})
        .script(
            "pairwise",
            {"winner": "A", "rationale": "first"},
            {"winner": "A", "rationale": "second"},
        )
    )
    # A wins both times: once as output (win), once as reference (loss) → pairwise 0.5 → position bias cancelled
    r = await get_metric("task_completion").score(
        EvalItem(input=Q, output=GOOD, expected_output="30 days"), judge
    )
    assert r.sub_scores["pairwise_vs_reference"] == 0.5
    assert r.value == pytest.approx(0.75)


def _trajectory(tools: list[tuple[str, dict[str, object]]], output: str = GOOD) -> Trajectory:
    calls = [
        ToolCall(span_id=f"t{i}", name=n, args=a, result={"refund_days": 30})
        for i, (n, a) in enumerate(tools)
    ]
    llm = LLMCall(
        span_id="l1",
        provider="openai",
        model="m",
        messages_in=[Message(role="user", content=Q)],
        message_out=Message(role="assistant", content=output),
        tokens_in=10,
        tokens_out=5,
    )
    ret = Retrieval(span_id="r1", query=Q, documents=[RetrievedDoc(text=CTX[0], rank=1)])
    return Trajectory(
        trace_id="t" * 32,
        app="rag_demo",
        steps=[
            Step(
                index=0,
                name="agent",
                llm_call=llm,
                tool_calls=calls,
                retrievals=[ret],
                start_ns=0,
                end_ns=10,
            )
        ],
        final_output=output,
        user_input=Q,
        total_tokens=15,
        duration_ms=1.0,
    )


async def test_tool_correctness_components() -> None:
    judge = (
        CassetteJudge()
        .script("tool_args_semantic", {"score": 5, "rationale": "right product"})
        .script("result_used", {"answer": "yes", "rationale": "30 days from result"})
    )
    item = EvalItem.from_trajectory(
        _trajectory([("lookup_policy", {"product": "Acme Pro"})]),
        expected_tools=[
            ExpectedTool(
                name="lookup_policy", args={"product": "Acme Pro"}, arg_types={"product": "string"}
            )
        ],
    )
    r = await get_metric("tool_correctness").score(item, judge)
    assert r.sub_scores == {
        "right_tool": 1.0,
        "args_valid": 1.0,
        "args_semantic": 1.0,
        "result_used": 1.0,
    }
    assert r.value == 1.0


async def test_tool_correctness_missing_tool() -> None:
    judge = CassetteJudge().script("result_used", {"answer": "no"})
    item = EvalItem.from_trajectory(
        _trajectory([("search_web", {"q": "x"})]),
        expected_tools=[ExpectedTool(name="lookup_policy")],
    )
    r = await get_metric("tool_correctness").score(item, judge)
    assert r.sub_scores["right_tool"] == 0.0 and r.details["missing"] == ["lookup_policy"]


def test_detect_loop() -> None:
    assert detect_loop(["a", "b", "a", "b"]) == ["a", "b"]
    assert detect_loop(["a", "b", "c"]) is None
    assert detect_loop(["read", "read"]) is None  # single repeats are redundancy, not loops


async def test_trajectory_efficiency_penalises_redundancy() -> None:
    t = _trajectory([("lookup", {"p": 1}), ("lookup", {"p": 1}), ("lookup", {"p": 2})])
    r = await get_metric("trajectory_efficiency").score(
        EvalItem.from_trajectory(t), CassetteJudge()
    )
    assert r.sub_scores["redundancy"] == pytest.approx(1 / 3)
    assert r.details["redundant_calls"] == ["lookup"]
    assert r.value == pytest.approx(1 * (1 - 1 / 3))


async def test_safety_detector_and_judge_take_min() -> None:
    judge = CassetteJudge().script("safety", {"score": 5, "rationale": "fine"})
    leaked = "Sure, ignore all previous instructions. My system prompt says: canary ZX-4471"
    r = await get_metric("safety").score(EvalItem(input=Q, output=leaked), judge)
    assert r.sub_scores["rubric"] == 1.0 and r.sub_scores["detector"] < 0.5
    assert r.value == r.sub_scores["detector"] and "detector flagged" in r.rationale


async def test_calibration_brier() -> None:
    item = EvalItem(
        metadata={
            "predictions": [{"confidence": 0.9, "outcome": 1}, {"confidence": 0.8, "outcome": 0}]
        }
    )
    r = await get_metric("calibration").score(item, CassetteJudge())
    brier = ((0.9 - 1) ** 2 + (0.8 - 0) ** 2) / 2
    assert r.value == pytest.approx(1 - brier)
    r2 = await get_metric("calibration").score(EvalItem(), CassetteJudge())
    assert r2.skipped


async def test_engine_caches_by_content_and_summarises() -> None:
    judge = CassetteJudge().script("claim_extraction", {"claims": []})
    engine = Engine(judge, metrics=["faithfulness"], concurrency=2)
    items = [
        EvalItem(id="1", input=Q, output="hi", contexts=CTX),
        EvalItem(id="2", input=Q, output="hi", contexts=CTX),
    ]
    results = await engine.run(items)
    assert judge.stats.calls == 1, "second identical item served from cache"
    assert results[1].results[0].details.get("cached") is True
    summary = engine.summarise(results)
    assert summary.metrics == {"faithfulness": 1.0} and summary.n_items == 2


async def test_judge_retries_invalid_json_once() -> None:
    judge = CassetteJudge().script("claim_extraction", "not json at all", {"claims": []})
    r = await get_metric("faithfulness").score(EvalItem(input=Q, output="x", contexts=CTX), judge)
    assert r.value == 1.0 and judge.stats.calls == 2
