"""Semantic-convention contract (SPEC.md §4). HARD CONTRACT.

Every attribute name accepted by Lens is declared here. ``normalize.py`` only
ever reads attributes through the helpers below; nothing else in the codebase
should mention a ``gen_ai.*`` / ``llm.*`` / ``traceloop.*`` string literal.

Sources
-------
* OTel GenAI semconv: ``gen_ai.*`` attributes, ``gen_ai.input.messages`` /
  ``gen_ai.output.messages`` (structured, semconv >= 1.37), the older span-event
  form (``gen_ai.content.prompt`` / ``gen_ai.content.completion`` and the
  per-role ``gen_ai.{system,user,assistant,tool}.message`` / ``gen_ai.choice``
  events), and ``gen_ai.operation.name`` for span kind.
* OpenLLMetry (Traceloop): current ``gen_ai.*`` names plus the legacy ``llm.*``
  names, indexed ``gen_ai.prompt.{i}.*`` / ``llm.prompts.{i}.*`` attributes, and
  ``traceloop.span.kind`` / ``traceloop.entity.*`` for workflows, tasks, tools
  and agents.
* Lens (``lens.*``): retrieval payloads, prompt version, session, feedback,
  expected output, run id.

Priority order is the order of each tuple below (first present wins).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, Final

from lens_core.trace.model import Message, SpanKind, ToolCallRequest

# ---------------------------------------------------------------------------------------------
# Attribute names
# ---------------------------------------------------------------------------------------------

# provider / model
GEN_AI_SYSTEM: Final = "gen_ai.system"
GEN_AI_PROVIDER_NAME: Final = "gen_ai.provider.name"  # semconv >= 1.37 rename of gen_ai.system
LLM_VENDOR: Final = "llm.vendor"
GEN_AI_REQUEST_MODEL: Final = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL: Final = "gen_ai.response.model"
LLM_REQUEST_MODEL: Final = "llm.request.model"
LLM_RESPONSE_MODEL: Final = "llm.response.model"

PROVIDER_ATTRS: Final[tuple[str, ...]] = (GEN_AI_SYSTEM, GEN_AI_PROVIDER_NAME, LLM_VENDOR)
MODEL_ATTRS: Final[tuple[str, ...]] = (
    GEN_AI_REQUEST_MODEL,
    LLM_REQUEST_MODEL,
    GEN_AI_RESPONSE_MODEL,
    LLM_RESPONSE_MODEL,
)

# operation / kind
GEN_AI_OPERATION_NAME: Final = "gen_ai.operation.name"
LLM_REQUEST_TYPE: Final = "llm.request.type"
TRACELOOP_SPAN_KIND: Final = "traceloop.span.kind"
TRACELOOP_ENTITY_NAME: Final = "traceloop.entity.name"
TRACELOOP_ENTITY_INPUT: Final = "traceloop.entity.input"
TRACELOOP_ENTITY_OUTPUT: Final = "traceloop.entity.output"
GEN_AI_AGENT_NAME: Final = "gen_ai.agent.name"

GEN_AI_OPERATION_LLM: Final[frozenset[str]] = frozenset(
    {"chat", "text_completion", "generate_content"}
)
GEN_AI_OPERATION_AGENT: Final[frozenset[str]] = frozenset({"invoke_agent", "create_agent"})
GEN_AI_OPERATION_TOOL: Final = "execute_tool"
GEN_AI_OPERATION_EMBEDDINGS: Final = "embeddings"
LLM_REQUEST_TYPE_LLM: Final[frozenset[str]] = frozenset({"chat", "completion", "rerank"})
LLM_REQUEST_TYPE_EMBEDDING: Final = "embedding"
TRACELOOP_KIND_AGENT: Final[frozenset[str]] = frozenset({"workflow", "agent"})
TRACELOOP_KIND_TOOL: Final = "tool"
TRACELOOP_KIND_TASK: Final = "task"

# messages
GEN_AI_INPUT_MESSAGES: Final = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES: Final = "gen_ai.output.messages"
GEN_AI_PROMPT_PREFIX: Final = "gen_ai.prompt."
GEN_AI_COMPLETION_PREFIX: Final = "gen_ai.completion."
LLM_PROMPTS_PREFIX: Final = "llm.prompts."
LLM_COMPLETIONS_PREFIX: Final = "llm.completions."
PROMPT_PREFIXES: Final[tuple[str, ...]] = (GEN_AI_PROMPT_PREFIX, LLM_PROMPTS_PREFIX)
COMPLETION_PREFIXES: Final[tuple[str, ...]] = (GEN_AI_COMPLETION_PREFIX, LLM_COMPLETIONS_PREFIX)

# span-event form of messages
EVENT_CONTENT_PROMPT: Final = "gen_ai.content.prompt"
EVENT_CONTENT_COMPLETION: Final = "gen_ai.content.completion"
EVENT_ATTR_PROMPT: Final = "gen_ai.prompt"
EVENT_ATTR_COMPLETION: Final = "gen_ai.completion"
EVENT_ROLE_MESSAGES: Final[dict[str, str]] = {
    "gen_ai.system.message": "system",
    "gen_ai.user.message": "user",
    "gen_ai.assistant.message": "assistant",
    "gen_ai.tool.message": "tool",
}
EVENT_CHOICE: Final = "gen_ai.choice"

# usage
INPUT_TOKEN_ATTRS: Final[tuple[str, ...]] = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
    "llm.usage.prompt_tokens",
)
OUTPUT_TOKEN_ATTRS: Final[tuple[str, ...]] = (
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
    "llm.usage.completion_tokens",
)
TEMPERATURE_ATTRS: Final[tuple[str, ...]] = (
    "gen_ai.request.temperature",
    "llm.request.temperature",
    "llm.temperature",
)
GEN_AI_RESPONSE_FINISH_REASONS: Final = "gen_ai.response.finish_reasons"

# tools
GEN_AI_TOOL_NAME: Final = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID: Final = "gen_ai.tool.call.id"
GEN_AI_TOOL_CALL_ARGUMENTS: Final = "gen_ai.tool.call.arguments"
GEN_AI_TOOL_CALL_RESULT: Final = "gen_ai.tool.call.result"

# retrieval
DB_SYSTEM: Final = "db.system"
DB_SYSTEM_NAME: Final = "db.system.name"
DB_SYSTEM_VECTOR: Final = "vector"
DB_QUERY_TEXT: Final = "db.query.text"
LENS_RETRIEVAL_QUERY: Final = "lens.retrieval.query"
LENS_RETRIEVAL_DOCS: Final = "lens.retrieval.docs"

# lens namespace
LENS_PROMPT_VERSION: Final = "lens.prompt.version"
LENS_SESSION_ID: Final = "lens.session.id"
LENS_USER_FEEDBACK: Final = "lens.user.feedback"
LENS_EVAL_EXPECTED_OUTPUT: Final = "lens.eval.expected_output"
LENS_RUN_ID: Final = "lens.run.id"

# resource
SERVICE_NAME: Final = "service.name"


# ---------------------------------------------------------------------------------------------
# Kind detection
# ---------------------------------------------------------------------------------------------


def detect_kind(attributes: Mapping[str, Any]) -> SpanKind:
    """Map raw attributes to a Lens ``SpanKind`` following SPEC.md §4 priority."""
    op = attributes.get(GEN_AI_OPERATION_NAME)
    if isinstance(op, str):
        if op in GEN_AI_OPERATION_AGENT:
            return "agent_step"
        if op == GEN_AI_OPERATION_TOOL:
            return "tool"
        if op == GEN_AI_OPERATION_EMBEDDINGS:
            return "embedding"
        if op in GEN_AI_OPERATION_LLM:
            return "llm"

    req_type = attributes.get(LLM_REQUEST_TYPE)
    if isinstance(req_type, str):
        if req_type == LLM_REQUEST_TYPE_EMBEDDING:
            return "embedding"
        if req_type in LLM_REQUEST_TYPE_LLM:
            return "llm"

    if GEN_AI_TOOL_NAME in attributes:
        return "tool"

    if (
        LENS_RETRIEVAL_QUERY in attributes
        or LENS_RETRIEVAL_DOCS in attributes
        or attributes.get(DB_SYSTEM) == DB_SYSTEM_VECTOR
        or attributes.get(DB_SYSTEM_NAME) == DB_SYSTEM_VECTOR
    ):
        return "retrieval"

    tl_kind = attributes.get(TRACELOOP_SPAN_KIND)
    if isinstance(tl_kind, str):
        if tl_kind in TRACELOOP_KIND_AGENT:
            return "agent_step"
        if tl_kind == TRACELOOP_KIND_TOOL:
            return "tool"
        if tl_kind == TRACELOOP_KIND_TASK:
            return "chain"

    if any(a in attributes for a in PROVIDER_ATTRS) and any(a in attributes for a in MODEL_ATTRS):
        return "llm"
    return "other"


# ---------------------------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------------------------


def first(attributes: Mapping[str, Any], keys: Iterable[str]) -> Any | None:
    for k in keys:
        if k in attributes and attributes[k] is not None:
            return attributes[k]
    return None


def as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def maybe_json(value: Any) -> Any:
    """Parse JSON-encoded strings; return other values unchanged."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "{[" or stripped in {"null", "true", "false"} or stripped[:1] == '"':
            try:
                return json.loads(stripped)
            except ValueError:
                return value
    return value


def indexed(attributes: Mapping[str, Any], prefix: str) -> dict[int, dict[str, Any]]:
    """Group ``<prefix><i>.<rest>`` attributes into ``{i: {rest: value}}``."""
    out: dict[int, dict[str, Any]] = {}
    for key, value in attributes.items():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix) :]
        idx_str, _, sub = rest.partition(".")
        if not idx_str.isdigit() or not sub:
            continue
        out.setdefault(int(idx_str), {})[sub] = value
    return out


def _nested_indexed(fields: Mapping[str, Any], prefix: str) -> list[dict[str, Any]]:
    grouped = indexed(fields, prefix)
    return [grouped[i] for i in sorted(grouped)]


# ---------------------------------------------------------------------------------------------
# Provider / model / usage
# ---------------------------------------------------------------------------------------------


def provider(attributes: Mapping[str, Any]) -> str:
    value = first(attributes, PROVIDER_ATTRS)
    return str(value).strip().lower() if value else "unknown"


def model(attributes: Mapping[str, Any]) -> str:
    value = first(attributes, MODEL_ATTRS)
    return str(value) if value else "unknown"


def tokens(attributes: Mapping[str, Any]) -> tuple[int, int]:
    return as_int(first(attributes, INPUT_TOKEN_ATTRS)), as_int(
        first(attributes, OUTPUT_TOKEN_ATTRS)
    )


def temperature(attributes: Mapping[str, Any]) -> float | None:
    return as_float(first(attributes, TEMPERATURE_ATTRS))


def finish_reason(
    attributes: Mapping[str, Any], completion: Mapping[str, Any] | None
) -> str | None:
    if completion and completion.get("finish_reason"):
        return str(completion["finish_reason"])
    reasons = maybe_json(attributes.get(GEN_AI_RESPONSE_FINISH_REASONS))
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    if isinstance(reasons, str) and reasons:
        return reasons
    return None


# ---------------------------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------------------------


def _tool_call_request(raw: Mapping[str, Any]) -> ToolCallRequest:
    """Accept OpenAI-style ``{id, function:{name, arguments}}`` or flat ``{id, name, arguments}``."""  # noqa: E501
    function = raw.get("function") if isinstance(raw.get("function"), Mapping) else None
    name = (function or raw).get("name")
    arguments = maybe_json((function or raw).get("arguments"))
    if not isinstance(arguments, dict | str) and arguments is not None:
        arguments = json.dumps(arguments)
    return ToolCallRequest(
        id=str(raw["id"]) if raw.get("id") is not None else None,
        name=str(name) if name is not None else "unknown",
        arguments=arguments,
    )


def _content_to_text(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        # OpenAI multi-part content: [{"type": "text", "text": "..."}]
        parts = [
            p.get("text") for p in content if isinstance(p, Mapping) and p.get("type") == "text"
        ]
        if parts and all(isinstance(p, str) for p in parts):
            return "".join(parts)
    return json.dumps(content, ensure_ascii=False)


def _message_from_dict(raw: Mapping[str, Any], default_role: str = "user") -> Message:
    """OpenAI-style message dict, or GenAI ``{role, parts:[...]}`` (semconv >= 1.37)."""
    role = str(raw.get("role") or default_role)
    tool_calls: list[ToolCallRequest] = []
    tool_call_id = raw.get("tool_call_id")
    content: str | None

    parts = raw.get("parts")
    if isinstance(parts, list):
        texts: list[str] = []
        for part in parts:
            if not isinstance(part, Mapping):
                continue
            ptype = part.get("type")
            if ptype == "text":
                texts.append(str(part.get("content", "")))
            elif ptype == "tool_call":
                tool_calls.append(_tool_call_request(part))
            elif ptype == "tool_call_response":
                tool_call_id = part.get("id", tool_call_id)
                resp = part.get("response", part.get("result"))
                texts.append(
                    resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
                )
        content = "".join(texts) if texts else None
    else:
        content = _content_to_text(raw.get("content"))
        raw_calls = maybe_json(raw.get("tool_calls"))
        if isinstance(raw_calls, list):
            tool_calls = [_tool_call_request(c) for c in raw_calls if isinstance(c, Mapping)]
        fc = maybe_json(raw.get("function_call"))
        if isinstance(fc, Mapping) and not tool_calls:
            tool_calls = [_tool_call_request(fc)]

    return Message(
        role=role,
        content=content,
        name=str(raw["name"]) if raw.get("name") is not None else None,
        tool_call_id=str(tool_call_id) if tool_call_id is not None else None,
        tool_calls=tool_calls,
    )


def _message_from_indexed(fields: Mapping[str, Any], default_role: str) -> Message:
    """Flattened ``role``/``content``/``tool_calls.{j}.*`` fields of one indexed message."""
    raw: dict[str, Any] = {
        k: v for k, v in fields.items() if k in ("role", "content", "name", "tool_call_id")
    }
    raw.setdefault("role", default_role)
    calls = _nested_indexed(fields, "tool_calls.")
    if calls:
        raw["tool_calls"] = calls
    elif any(k.startswith("function_call.") for k in fields):
        raw["function_call"] = {
            k.removeprefix("function_call."): v
            for k, v in fields.items()
            if k.startswith("function_call.")
        }
    return _message_from_dict(raw, default_role)


def _event_messages(
    events: Iterable[Mapping[str, Any]],
) -> tuple[list[Message], Message | None, str | None]:
    """Extract messages from span events (both event conventions)."""
    messages_in: list[Message] = []
    message_out: Message | None = None
    fin: str | None = None
    for ev in events:
        name = ev.get("name")
        attrs: Mapping[str, Any] = ev.get("attributes") or {}
        if name == EVENT_CONTENT_PROMPT:
            payload = maybe_json(attrs.get(EVENT_ATTR_PROMPT))
            if isinstance(payload, list):
                messages_in.extend(_message_from_dict(m) for m in payload if isinstance(m, Mapping))
        elif name == EVENT_CONTENT_COMPLETION:
            payload = maybe_json(attrs.get(EVENT_ATTR_COMPLETION))
            if isinstance(payload, list) and payload and isinstance(payload[0], Mapping):
                message_out = _message_from_dict(payload[0], "assistant")
                fin = payload[0].get("finish_reason") or fin
            elif isinstance(payload, Mapping):
                message_out = _message_from_dict(payload, "assistant")
                fin = payload.get("finish_reason") or fin
        elif isinstance(name, str) and name in EVENT_ROLE_MESSAGES:
            body: dict[str, Any] = dict(attrs)
            body.setdefault("role", EVENT_ROLE_MESSAGES[name])
            if "id" in body and "tool_call_id" not in body:
                body["tool_call_id"] = body.pop("id")
            messages_in.append(_message_from_dict(body, EVENT_ROLE_MESSAGES[name]))
        elif name == EVENT_CHOICE:
            msg = maybe_json(attrs.get("message"))
            if isinstance(msg, Mapping):
                message_out = _message_from_dict(msg, "assistant")
            elif "content" in attrs or "tool_calls" in attrs:
                message_out = _message_from_dict(attrs, "assistant")
            fin = attrs.get("finish_reason") or fin
    return messages_in, message_out, (str(fin) if fin else None)


def messages_in(
    attributes: Mapping[str, Any], events: Iterable[Mapping[str, Any]]
) -> list[Message]:
    structured = maybe_json(attributes.get(GEN_AI_INPUT_MESSAGES))
    if isinstance(structured, list) and structured:
        return [_message_from_dict(m) for m in structured if isinstance(m, Mapping)]
    for prefix in PROMPT_PREFIXES:
        grouped = indexed(attributes, prefix)
        if grouped:
            return [_message_from_indexed(grouped[i], "user") for i in sorted(grouped)]
    msgs, _, _ = _event_messages(events)
    return msgs


def message_out(
    attributes: Mapping[str, Any], events: Iterable[Mapping[str, Any]]
) -> tuple[Message | None, str | None]:
    """Return ``(first completion message, finish_reason)``."""
    structured = maybe_json(attributes.get(GEN_AI_OUTPUT_MESSAGES))
    if isinstance(structured, list) and structured and isinstance(structured[0], Mapping):
        msg = _message_from_dict(structured[0], "assistant")
        return msg, finish_reason(attributes, structured[0])
    for prefix in COMPLETION_PREFIXES:
        grouped = indexed(attributes, prefix)
        if grouped:
            fields = grouped[min(grouped)]
            return _message_from_indexed(fields, "assistant"), finish_reason(attributes, fields)
    _, msg, fin = _event_messages(events)
    return msg, fin or finish_reason(attributes, None)


# ---------------------------------------------------------------------------------------------
# Tools & retrieval
# ---------------------------------------------------------------------------------------------


def entity_kwargs(value: Any) -> dict[str, Any]:
    """Turn ``traceloop.entity.input`` (``{"args": [...], "kwargs": {...}}``) into an args dict."""
    parsed = maybe_json(value)
    if isinstance(parsed, Mapping):
        if "kwargs" in parsed or "args" in parsed:
            out: dict[str, Any] = dict(parsed.get("kwargs") or {})
            args = parsed.get("args")
            if args:
                out["args"] = args
            return out
        return dict(parsed)
    if parsed is None:
        return {}
    return {"input": parsed}


def tool_fields(
    attributes: Mapping[str, Any], span_name: str
) -> tuple[str, str | None, dict[str, Any], Any]:
    """``(name, call_id, args, result)`` for a tool-execution span."""
    name = first(attributes, (GEN_AI_TOOL_NAME, TRACELOOP_ENTITY_NAME)) or span_name
    call_id = attributes.get(GEN_AI_TOOL_CALL_ID)
    args: dict[str, Any]
    if GEN_AI_TOOL_CALL_ARGUMENTS in attributes:
        parsed = maybe_json(attributes[GEN_AI_TOOL_CALL_ARGUMENTS])
        args = dict(parsed) if isinstance(parsed, Mapping) else {"input": parsed}
    else:
        args = entity_kwargs(attributes.get(TRACELOOP_ENTITY_INPUT))
    result = maybe_json(first(attributes, (GEN_AI_TOOL_CALL_RESULT, TRACELOOP_ENTITY_OUTPUT)))
    return str(name), (str(call_id) if call_id is not None else None), args, result


def retrieval_fields(attributes: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """``(query, docs)`` for a retrieval span. Docs come from ``lens.retrieval.docs`` or
    ``traceloop.entity.output`` (a JSON list of ``{id?, text, score?, rank?}``)."""
    query = first(attributes, (LENS_RETRIEVAL_QUERY, DB_QUERY_TEXT))
    if query is None:
        kwargs = entity_kwargs(attributes.get(TRACELOOP_ENTITY_INPUT))
        query = (
            kwargs.get("query")
            or kwargs.get("input")
            or (next(iter(kwargs.values())) if len(kwargs) == 1 else None)
        )
    raw_docs = maybe_json(first(attributes, (LENS_RETRIEVAL_DOCS, TRACELOOP_ENTITY_OUTPUT)))
    docs: list[dict[str, Any]] = []
    if isinstance(raw_docs, list):
        for d in raw_docs:
            if isinstance(d, Mapping):
                docs.append(dict(d))
            elif isinstance(d, str):
                docs.append({"text": d})
    return (str(query) if query is not None else ""), docs
