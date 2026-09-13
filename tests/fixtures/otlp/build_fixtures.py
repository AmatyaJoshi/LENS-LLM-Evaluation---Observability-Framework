"""Generate the four conformance fixtures (SPEC.md §4): one logical RAG-agent run, recorded as
(a) OpenLLMetry Python, (b) OpenLLMetry TS (legacy ``llm.*`` names), (c) raw OTel GenAI
semconv (span-event messages), (d) Lens SDK (structured ``gen_ai.input/output.messages``).

Run ``python tests/fixtures/otlp/build_fixtures.py`` to regenerate. Deterministic.

The logical run
---------------
rag_pipeline (agent)
  ├── retrieve_docs (retrieval)  q="What is the refund window for Acme Pro?" -> 2 docs
  ├── openai.chat (llm #1)       -> tool_call lookup_policy(product="Acme Pro")
  ├── lookup_policy (tool)       -> {"refund_days": 30}
  └── openai.chat (llm #2)       -> final answer
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).parent

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
ROOT, RET, LLM1, TOOL, LLM2 = (
    "b7ad6b7169203331",
    "1111111111111111",
    "2222222222222222",
    "3333333333333333",
    "4444444444444444",
)
T0 = 1_700_000_000_000_000_000
MS = 1_000_000

SYS = "You are Acme's support assistant. Answer only from the provided context."
Q = "What is the refund window for Acme Pro?"
DOCS = [
    {
        "id": "doc-17",
        "text": "Acme Pro purchases can be refunded within 30 days of purchase.",
        "score": 0.91,
    },
    {"id": "doc-42", "text": "Acme Basic has a 14-day refund window.", "score": 0.77},
]
USER = "Context:\n" + "\n".join(f"[{d['id']}] {d['text']}" for d in DOCS) + f"\n\nQuestion: {Q}"
ANSWER = "Acme Pro purchases can be refunded within 30 days of purchase."
ARGS = {"product": "Acme Pro"}
ARGS_JSON = json.dumps(ARGS)
TOOL_RESULT = {"refund_days": 30}
TOOL_RESULT_JSON = json.dumps(TOOL_RESULT)
CALL_ID = "call_1"

OPENAI_TOOL_CALL = {
    "id": CALL_ID,
    "type": "function",
    "function": {"name": "lookup_policy", "arguments": ARGS_JSON},
}

# ---------------------------------------------------------------------------------------------
# OTLP/JSON encoding helpers
# ---------------------------------------------------------------------------------------------


def av(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [av(v) for v in value]}}
    return {"stringValue": str(value)}


def attrs(d: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": k, "value": av(v)} for k, v in d.items()]


def span(
    sid: str,
    name: str,
    start_ms: int,
    end_ms: int,
    a: dict[str, Any],
    parent: str | None = ROOT,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    s: dict[str, Any] = {
        "traceId": TRACE_ID,
        "spanId": sid,
        "name": name,
        "kind": 1,
        "startTimeUnixNano": str(T0 + start_ms * MS),
        "endTimeUnixNano": str(T0 + end_ms * MS),
        "attributes": attrs(a),
        "status": {},
    }
    if parent:
        s["parentSpanId"] = parent
    if events:
        s["events"] = events
    return s


def event(name: str, time_ms: int, a: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "timeUnixNano": str(T0 + time_ms * MS), "attributes": attrs(a)}


def request(resource: dict[str, Any], scope: str, spans: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": attrs(resource)},
                "scopeSpans": [{"scope": {"name": scope}, "spans": spans}],
            }
        ]
    }


ROOT_LENS = {"lens.session.id": "sess-001", "lens.run.id": "run-7"}

# ---------------------------------------------------------------------------------------------
# (a) OpenLLMetry Python — current gen_ai.* names + traceloop.* decorators
# ---------------------------------------------------------------------------------------------


def openllmetry_python() -> dict[str, Any]:
    def llm(
        sid: str,
        start: int,
        end: int,
        prompts: list[dict[str, Any]],
        completion: dict[str, Any],
        tin: int,
        tout: int,
    ):
        a: dict[str, Any] = {
            "gen_ai.system": "OpenAI",
            "llm.request.type": "chat",
            "gen_ai.request.model": "gpt-4o-mini",
            "gen_ai.response.model": "gpt-4o-mini-2024-07-18",
            "gen_ai.usage.prompt_tokens": tin,
            "gen_ai.usage.completion_tokens": tout,
            "llm.usage.total_tokens": tin + tout,
            "llm.is_streaming": False,
        }
        for i, p in enumerate(prompts):
            for k, v in p.items():
                a[f"gen_ai.prompt.{i}.{k}"] = v
        for k, v in completion.items():
            a[f"gen_ai.completion.0.{k}"] = v
        return span(sid, "openai.chat", start, end, a)

    tool_call_prompt = {
        "role": "assistant",
        "tool_calls.0.id": CALL_ID,
        "tool_calls.0.name": "lookup_policy",
        "tool_calls.0.arguments": ARGS_JSON,
    }
    spans = [
        span(
            ROOT,
            "rag_pipeline.workflow",
            0,
            2000,
            {
                "traceloop.span.kind": "workflow",
                "traceloop.entity.name": "rag_pipeline",
                "traceloop.entity.input": json.dumps({"args": [], "kwargs": {"question": Q}}),
                "traceloop.entity.output": json.dumps(ANSWER),
                **ROOT_LENS,
            },
            parent=None,
        ),
        span(
            RET,
            "retrieve_docs.task",
            10,
            110,
            {
                "traceloop.span.kind": "task",
                "traceloop.entity.name": "retrieve_docs",
                "lens.retrieval.query": Q,
                "lens.retrieval.docs": json.dumps(DOCS),
            },
        ),
        llm(
            LLM1,
            120,
            900,
            [{"role": "system", "content": SYS}, {"role": "user", "content": USER}],
            {
                "role": "assistant",
                "finish_reason": "tool_calls",
                "tool_calls.0.id": CALL_ID,
                "tool_calls.0.name": "lookup_policy",
                "tool_calls.0.arguments": ARGS_JSON,
            },
            182,
            21,
        ),
        span(
            TOOL,
            "lookup_policy.tool",
            910,
            960,
            {
                "traceloop.span.kind": "tool",
                "traceloop.entity.name": "lookup_policy",
                "traceloop.entity.input": json.dumps({"args": [], "kwargs": ARGS}),
                "traceloop.entity.output": TOOL_RESULT_JSON,
            },
        ),
        llm(
            LLM2,
            970,
            1950,
            [
                {"role": "system", "content": SYS},
                {"role": "user", "content": USER},
                tool_call_prompt,
                {"role": "tool", "content": TOOL_RESULT_JSON, "tool_call_id": CALL_ID},
            ],
            {"role": "assistant", "content": ANSWER, "finish_reason": "stop"},
            231,
            16,
        ),
    ]
    return request(
        {
            "service.name": "rag_demo",
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
        },
        "opentelemetry.instrumentation.openai.v1",
        spans,
    )


# ---------------------------------------------------------------------------------------------
# (b) OpenLLMetry TS — legacy llm.* names
# ---------------------------------------------------------------------------------------------


def openllmetry_ts() -> dict[str, Any]:
    def llm(
        sid: str,
        start: int,
        end: int,
        prompts: list[dict[str, Any]],
        completion: dict[str, Any],
        tin: int,
        tout: int,
    ):
        a: dict[str, Any] = {
            "llm.vendor": "openai",
            "llm.request.type": "chat",
            "llm.request.model": "gpt-4o-mini",
            "llm.response.model": "gpt-4o-mini-2024-07-18",
            "llm.usage.prompt_tokens": tin,
            "llm.usage.completion_tokens": tout,
            "llm.usage.total_tokens": tin + tout,
        }
        for i, p in enumerate(prompts):
            for k, v in p.items():
                a[f"llm.prompts.{i}.{k}"] = v
        for k, v in completion.items():
            a[f"llm.completions.0.{k}"] = v
        return span(sid, "openai.chat", start, end, a)

    spans = [
        span(
            ROOT,
            "rag_pipeline.workflow",
            0,
            2000,
            {
                "traceloop.span.kind": "workflow",
                "traceloop.entity.name": "rag_pipeline",
                "traceloop.entity.input": json.dumps({"args": [Q], "kwargs": {}}),
                "traceloop.entity.output": json.dumps(ANSWER),
                **ROOT_LENS,
            },
            parent=None,
        ),
        span(
            RET,
            "retrieve_docs.task",
            10,
            110,
            {
                "traceloop.span.kind": "task",
                "traceloop.entity.name": "retrieve_docs",
                "lens.retrieval.query": Q,
                # docs via the generic task output rather than lens.retrieval.docs
                "traceloop.entity.output": json.dumps(DOCS),
            },
        ),
        llm(
            LLM1,
            120,
            900,
            [{"role": "system", "content": SYS}, {"role": "user", "content": USER}],
            {
                "role": "assistant",
                "finish_reason": "tool_calls",
                "tool_calls.0.id": CALL_ID,
                "tool_calls.0.name": "lookup_policy",
                "tool_calls.0.arguments": ARGS_JSON,
            },
            182,
            21,
        ),
        span(
            TOOL,
            "lookup_policy.tool",
            910,
            960,
            {
                "traceloop.span.kind": "tool",
                "traceloop.entity.name": "lookup_policy",
                "traceloop.entity.input": json.dumps({"args": [], "kwargs": ARGS}),
                "traceloop.entity.output": TOOL_RESULT_JSON,
            },
        ),
        llm(
            LLM2,
            970,
            1950,
            [
                {"role": "system", "content": SYS},
                {"role": "user", "content": USER},
                {
                    "role": "assistant",
                    "tool_calls.0.id": CALL_ID,
                    "tool_calls.0.name": "lookup_policy",
                    "tool_calls.0.arguments": ARGS_JSON,
                },
                {"role": "tool", "content": TOOL_RESULT_JSON, "tool_call_id": CALL_ID},
            ],
            {"role": "assistant", "content": ANSWER, "finish_reason": "stop"},
            231,
            16,
        ),
    ]
    return request(
        {
            "service.name": "rag_demo",
            "telemetry.sdk.language": "nodejs",
            "telemetry.sdk.name": "opentelemetry",
        },
        "@traceloop/instrumentation-openai",
        spans,
    )


# ---------------------------------------------------------------------------------------------
# (c) raw OTel GenAI semconv — gen_ai.operation.name, usage.input/output_tokens, event messages
# ---------------------------------------------------------------------------------------------


def otel_genai() -> dict[str, Any]:
    def llm(
        sid: str,
        start: int,
        end: int,
        prompt: list[dict[str, Any]],
        completion: dict[str, Any],
        tin: int,
        tout: int,
    ):
        a = {
            "gen_ai.operation.name": "chat",
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4o-mini",
            "gen_ai.response.model": "gpt-4o-mini-2024-07-18",
            "gen_ai.response.finish_reasons": [completion["finish_reason"]],
            "gen_ai.usage.input_tokens": tin,
            "gen_ai.usage.output_tokens": tout,
            "server.address": "api.openai.com",
        }
        return span(
            sid,
            "chat gpt-4o-mini",
            start,
            end,
            a,
            events=[
                event("gen_ai.content.prompt", start, {"gen_ai.prompt": json.dumps(prompt)}),
                event(
                    "gen_ai.content.completion",
                    end,
                    {"gen_ai.completion": json.dumps([completion])},
                ),
            ],
        )

    spans = [
        span(
            ROOT,
            "invoke_agent rag_pipeline",
            0,
            2000,
            {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": "rag_pipeline",
                **ROOT_LENS,
            },
            parent=None,
        ),
        span(
            RET,
            "vector.query acme_docs",
            10,
            110,
            {
                "db.system": "vector",
                "db.collection.name": "acme_docs",
                "db.query.text": Q,
                "lens.retrieval.docs": json.dumps(DOCS),
            },
        ),
        llm(
            LLM1,
            120,
            900,
            [{"role": "system", "content": SYS}, {"role": "user", "content": USER}],
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [OPENAI_TOOL_CALL],
                "finish_reason": "tool_calls",
            },
            182,
            21,
        ),
        span(
            TOOL,
            "execute_tool lookup_policy",
            910,
            960,
            {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": "lookup_policy",
                "gen_ai.tool.call.id": CALL_ID,
                "gen_ai.tool.call.arguments": ARGS_JSON,
                "gen_ai.tool.call.result": TOOL_RESULT_JSON,
            },
        ),
        llm(
            LLM2,
            970,
            1950,
            [
                {"role": "system", "content": SYS},
                {"role": "user", "content": USER},
                {"role": "assistant", "content": None, "tool_calls": [OPENAI_TOOL_CALL]},
                {"role": "tool", "content": TOOL_RESULT_JSON, "tool_call_id": CALL_ID},
            ],
            {"role": "assistant", "content": ANSWER, "finish_reason": "stop"},
            231,
            16,
        ),
    ]
    return request(
        {
            "service.name": "rag_demo",
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
        },
        "opentelemetry.instrumentation.openai_v2",
        spans,
    )


# ---------------------------------------------------------------------------------------------
# (d) Lens SDK — structured gen_ai.input/output.messages (semconv >= 1.37) + lens.* helpers
# ---------------------------------------------------------------------------------------------


def lens_sdk() -> dict[str, Any]:
    def text(role: str, content: str) -> dict[str, Any]:
        return {"role": role, "parts": [{"type": "text", "content": content}]}

    tool_call_msg = {
        "role": "assistant",
        "parts": [{"type": "tool_call", "id": CALL_ID, "name": "lookup_policy", "arguments": ARGS}],
    }
    tool_resp_msg = {
        "role": "tool",
        "parts": [{"type": "tool_call_response", "id": CALL_ID, "response": TOOL_RESULT}],
    }

    def llm(
        sid: str,
        start: int,
        end: int,
        inp: list[dict[str, Any]],
        out: dict[str, Any],
        tin: int,
        tout: int,
    ):
        a = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o-mini",
            "gen_ai.usage.input_tokens": tin,
            "gen_ai.usage.output_tokens": tout,
            "gen_ai.input.messages": json.dumps(inp),
            "gen_ai.output.messages": json.dumps([out]),
        }
        return span(sid, "chat gpt-4o-mini", start, end, a)

    spans = [
        span(
            ROOT,
            "rag_pipeline",
            0,
            2000,
            {"traceloop.span.kind": "agent", "traceloop.entity.name": "rag_pipeline", **ROOT_LENS},
            parent=None,
        ),
        span(
            RET,
            "retrieve_docs",
            10,
            110,
            {"lens.retrieval.query": Q, "lens.retrieval.docs": json.dumps(DOCS)},
        ),
        llm(
            LLM1,
            120,
            900,
            [text("system", SYS), text("user", USER)],
            {**tool_call_msg, "finish_reason": "tool_calls"},
            182,
            21,
        ),
        span(
            TOOL,
            "lookup_policy",
            910,
            960,
            {
                "gen_ai.tool.name": "lookup_policy",
                "gen_ai.tool.call.id": CALL_ID,
                "gen_ai.tool.call.arguments": ARGS_JSON,
                "gen_ai.tool.call.result": TOOL_RESULT_JSON,
            },
        ),
        llm(
            LLM2,
            970,
            1950,
            [text("system", SYS), text("user", USER), tool_call_msg, tool_resp_msg],
            {**text("assistant", ANSWER), "finish_reason": "stop"},
            231,
            16,
        ),
    ]
    return request(
        {
            "service.name": "rag_demo",
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "lens",
        },
        "lens_sdk",
        spans,
    )


FIXTURES = {
    "openllmetry_python": openllmetry_python,
    "openllmetry_ts": openllmetry_ts,
    "otel_genai": otel_genai,
    "lens_sdk": lens_sdk,
}


def main() -> None:
    for name, fn in FIXTURES.items():
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(fn(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", path.relative_to(OUT.parents[2]))


if __name__ == "__main__":
    main()
