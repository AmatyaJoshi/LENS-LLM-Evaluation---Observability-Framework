"""Span store: ClickHouse (production) and in-memory (tests / --lite dev).

Schema lives in ``apps/api/migrations/clickhouse/*.sql`` and is applied by
``run_migrations`` at API start-up; never hand-edit the live schema (CLAUDE.md).

Both implementations expose the same read API: per-trace summaries with
server-side filtering/search/pagination, aggregate overview statistics for the
dashboard, and the list of known apps.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from lens_api.ingest import normalize, semconv
from lens_api.settings import Settings
from lens_core.trace.model import Span, SpanEvent

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "clickhouse"
PREVIEW_CHARS = 240

COLUMNS: tuple[str, ...] = (
    "trace_id",
    "span_id",
    "parent_span_id",
    "app",
    "name",
    "kind",
    "start_ns",
    "end_ns",
    "duration_ms",
    "status",
    "status_message",
    "provider",
    "model",
    "tokens_in",
    "tokens_out",
    "attributes",
    "resource",
    "events",
    "truncated_attributes",
    "input_preview",
    "output_preview",
    "run_id",
    "session_id",
)


# ---------------------------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------------------------


class TraceFilter(BaseModel):
    app: str | None = None
    status: str | None = None  # ok | error
    model: str | None = None
    provider: str | None = None
    kind: str | None = None  # trace contains at least one span of this kind
    q: str | None = None  # substring on trace id, root name, input/output previews
    since_ns: int | None = None
    until_ns: int | None = None
    min_duration_ms: float | None = None
    max_duration_ms: float | None = None
    has_tools: bool | None = None
    has_retrievals: bool | None = None
    limit: int = 50
    offset: int = 0
    sort: str = "start_desc"  # start_desc | start_asc | duration_desc | tokens_desc


class TraceSummary(BaseModel):
    trace_id: str
    app: str
    root_name: str
    start_ns: int
    end_ns: int
    duration_ms: float
    span_count: int
    llm_calls: int
    tool_calls: int
    retrievals: int
    errors: int
    tokens_in: int
    tokens_out: int
    models: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    status: str
    input_preview: str | None = None
    output_preview: str | None = None
    truncated: bool = False
    run_id: str | None = None
    session_id: str | None = None


class TracePage(BaseModel):
    items: list[TraceSummary]
    total: int
    limit: int
    offset: int


class SeriesPoint(BaseModel):
    t_ns: int
    traces: int
    errors: int
    tokens: int
    p95_ms: float


class ModelUsage(BaseModel):
    model: str
    provider: str
    calls: int
    tokens_in: int
    tokens_out: int


class AppUsage(BaseModel):
    app: str
    traces: int
    errors: int
    last_seen_ns: int


class OverviewStats(BaseModel):
    since_ns: int
    until_ns: int
    bucket_ns: int
    traces: int = 0
    spans: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    retrievals: int = 0
    errors: int = 0
    error_rate: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    avg_ms: float = 0.0
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_model: list[ModelUsage] = Field(default_factory=list)
    by_app: list[AppUsage] = Field(default_factory=list)
    series: list[SeriesPoint] = Field(default_factory=list)


class SpanStore(Protocol):
    async def insert_spans(self, spans: Sequence[Span]) -> int: ...
    async def get_trace(self, trace_id: str) -> list[Span]: ...
    async def list_traces(self, flt: TraceFilter) -> TracePage: ...
    async def overview(
        self, *, app: str | None, since_ns: int, until_ns: int, bucket_ns: int
    ) -> OverviewStats: ...
    async def list_apps(self) -> list[AppUsage]: ...
    async def ping(self) -> bool: ...


# ---------------------------------------------------------------------------------------------
# Row mapping
# ---------------------------------------------------------------------------------------------


def _clip(text: str | None) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1] + "…"


def previews(span: Span) -> tuple[str, str]:
    """``(input_preview, output_preview)`` for an LLM span, else empty strings."""
    if span.kind != "llm":
        return "", ""
    call = normalize.derive_llm_call(span)
    user = next((m.content for m in call.messages_in if m.role == "user" and m.content), None)
    out = call.message_out.content if call.message_out else None
    return _clip(user), _clip(out)


def span_to_row(span: Span, app: str) -> list[Any]:
    tokens_in, tokens_out = semconv.tokens(span.attributes) if span.kind == "llm" else (0, 0)
    inp, out = previews(span)
    return [
        span.trace_id,
        span.span_id,
        span.parent_span_id or "",
        app,
        span.name,
        span.kind,
        span.start_ns,
        span.end_ns,
        span.duration_ms,
        span.status,
        span.status_message or "",
        semconv.provider(span.attributes) if span.kind == "llm" else "",
        semconv.model(span.attributes) if span.kind == "llm" else "",
        tokens_in,
        tokens_out,
        json.dumps(span.attributes, ensure_ascii=False, default=str),
        json.dumps(span.resource, ensure_ascii=False, default=str),
        json.dumps([e.model_dump() for e in span.events], ensure_ascii=False, default=str),
        list(span.truncated_attributes),
        inp,
        out,
        str(span.attributes.get(semconv.LENS_RUN_ID) or ""),
        str(span.attributes.get(semconv.LENS_SESSION_ID) or ""),
    ]


def row_to_span(row: dict[str, Any]) -> Span:
    return Span(
        trace_id=row["trace_id"],
        span_id=row["span_id"],
        parent_span_id=row["parent_span_id"] or None,
        name=row["name"],
        kind=row["kind"],
        start_ns=int(row["start_ns"]),
        end_ns=int(row["end_ns"]),
        status=row["status"],
        status_message=row["status_message"] or None,
        attributes=json.loads(row["attributes"] or "{}"),
        resource=json.loads(row["resource"] or "{}"),
        events=[SpanEvent(**e) for e in json.loads(row["events"] or "[]")],
        truncated_attributes=list(row.get("truncated_attributes") or []),
    )


def summarise(trace_id: str, spans: Iterable[Span]) -> TraceSummary:
    spans = sorted(spans, key=lambda s: (s.start_ns, s.span_id))
    by_id = {s.span_id: s for s in spans}
    roots = [s for s in spans if not s.parent_span_id or s.parent_span_id not in by_id]
    root = min(roots or spans, key=lambda s: s.start_ns)
    start = min(s.start_ns for s in spans)
    end = max(s.end_ns for s in spans)
    llm_spans = [s for s in spans if s.kind == "llm"]
    tokens = [semconv.tokens(s.attributes) for s in llm_spans]
    inp = next((p for p in (previews(s)[0] for s in llm_spans) if p), None)
    out = next((p for p in (previews(s)[1] for s in reversed(llm_spans)) if p), None)
    run_id = next(
        (
            s.attributes.get(semconv.LENS_RUN_ID)
            for s in spans
            if semconv.LENS_RUN_ID in s.attributes
        ),
        None,
    )
    session_id = next(
        (
            s.attributes.get(semconv.LENS_SESSION_ID)
            for s in spans
            if semconv.LENS_SESSION_ID in s.attributes
        ),
        None,
    )
    return TraceSummary(
        trace_id=trace_id,
        app=normalize.app_of(root),
        root_name=root.name,
        start_ns=start,
        end_ns=end,
        duration_ms=(end - start) / 1_000_000,
        span_count=len(spans),
        llm_calls=len(llm_spans),
        tool_calls=sum(1 for s in spans if s.kind == "tool"),
        retrievals=sum(1 for s in spans if s.kind == "retrieval"),
        errors=sum(1 for s in spans if s.status == "error"),
        tokens_in=sum(t[0] for t in tokens),
        tokens_out=sum(t[1] for t in tokens),
        models=sorted({semconv.model(s.attributes) for s in llm_spans}),
        providers=sorted({semconv.provider(s.attributes) for s in llm_spans}),
        status="error" if any(s.status == "error" for s in spans) else "ok",
        input_preview=inp,
        output_preview=out,
        truncated=any(s.truncated_attributes for s in spans),
        run_id=str(run_id) if run_id is not None else None,
        session_id=str(session_id) if session_id is not None else None,
    )


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(p * (len(ordered) - 1))))
    return float(ordered[idx])


# ---------------------------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------------------------


class InMemorySpanStore:
    def __init__(self) -> None:
        self._spans: dict[str, dict[str, Span]] = defaultdict(dict)

    async def insert_spans(self, spans: Sequence[Span]) -> int:
        for s in spans:
            self._spans[s.trace_id][s.span_id] = s
        return len(spans)

    async def get_trace(self, trace_id: str) -> list[Span]:
        return sorted(self._spans.get(trace_id, {}).values(), key=lambda s: (s.start_ns, s.span_id))

    def _summaries(self) -> list[TraceSummary]:
        return [summarise(tid, spans.values()) for tid, spans in self._spans.items() if spans]

    @staticmethod
    def _matches(s: TraceSummary, f: TraceFilter) -> bool:
        if f.app and s.app != f.app:
            return False
        if f.status and s.status != f.status:
            return False
        if f.model and f.model not in s.models:
            return False
        if f.provider and f.provider not in s.providers:
            return False
        if f.since_ns is not None and s.start_ns < f.since_ns:
            return False
        if f.until_ns is not None and s.start_ns > f.until_ns:
            return False
        if f.min_duration_ms is not None and s.duration_ms < f.min_duration_ms:
            return False
        if f.max_duration_ms is not None and s.duration_ms > f.max_duration_ms:
            return False
        if f.has_tools is not None and (s.tool_calls > 0) != f.has_tools:
            return False
        if f.has_retrievals is not None and (s.retrievals > 0) != f.has_retrievals:
            return False
        if f.kind:
            counts = {"llm": s.llm_calls, "tool": s.tool_calls, "retrieval": s.retrievals}
            if counts.get(f.kind, 0) == 0:
                return False
        if f.q:
            q = f.q.lower()
            hay = " ".join(
                x
                for x in (s.trace_id, s.root_name, s.input_preview, s.output_preview, s.run_id)
                if x
            ).lower()
            if q not in hay:
                return False
        return True

    async def list_traces(self, flt: TraceFilter) -> TracePage:
        items = [s for s in self._summaries() if self._matches(s, flt)]
        key = {
            "start_asc": (lambda s: s.start_ns, False),
            "duration_desc": (lambda s: s.duration_ms, True),
            "tokens_desc": (lambda s: s.tokens_in + s.tokens_out, True),
        }.get(flt.sort, (lambda s: s.start_ns, True))
        items.sort(key=key[0], reverse=key[1])
        return TracePage(
            items=items[flt.offset : flt.offset + flt.limit],
            total=len(items),
            limit=flt.limit,
            offset=flt.offset,
        )

    async def overview(
        self, *, app: str | None, since_ns: int, until_ns: int, bucket_ns: int
    ) -> OverviewStats:
        sums = [
            s
            for s in self._summaries()
            if since_ns <= s.start_ns <= until_ns and (not app or s.app == app)
        ]
        stats = OverviewStats(since_ns=since_ns, until_ns=until_ns, bucket_ns=bucket_ns)
        stats.traces = len(sums)
        stats.errors = sum(1 for s in sums if s.status == "error")
        stats.error_rate = stats.errors / stats.traces if stats.traces else 0.0
        stats.tokens_in = sum(s.tokens_in for s in sums)
        stats.tokens_out = sum(s.tokens_out for s in sums)
        durations = [s.duration_ms for s in sums]
        stats.p50_ms = _percentile(durations, 0.5)
        stats.p95_ms = _percentile(durations, 0.95)
        stats.avg_ms = sum(durations) / len(durations) if durations else 0.0

        kinds: Counter[str] = Counter()
        models: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
        for s in sums:
            for span in self._spans[s.trace_id].values():
                kinds[span.kind] += 1
                if span.kind == "llm":
                    ti, to = semconv.tokens(span.attributes)
                    m = models[(semconv.model(span.attributes), semconv.provider(span.attributes))]
                    m[0] += 1
                    m[1] += ti
                    m[2] += to
        stats.spans = sum(kinds.values())
        stats.llm_calls = kinds.get("llm", 0)
        stats.tool_calls = kinds.get("tool", 0)
        stats.retrievals = kinds.get("retrieval", 0)
        stats.by_kind = dict(kinds)
        stats.by_model = sorted(
            (
                ModelUsage(model=k[0], provider=k[1], calls=v[0], tokens_in=v[1], tokens_out=v[2])
                for k, v in models.items()
            ),
            key=lambda m: m.calls,
            reverse=True,
        )
        apps: dict[str, AppUsage] = {}
        for s in sums:
            a = apps.setdefault(s.app, AppUsage(app=s.app, traces=0, errors=0, last_seen_ns=0))
            a.traces += 1
            a.errors += 1 if s.status == "error" else 0
            a.last_seen_ns = max(a.last_seen_ns, s.start_ns)
        stats.by_app = sorted(apps.values(), key=lambda a: a.traces, reverse=True)

        buckets: dict[int, list[TraceSummary]] = defaultdict(list)
        for s in sums:
            buckets[(s.start_ns // bucket_ns) * bucket_ns].append(s)
        stats.series = [
            SeriesPoint(
                t_ns=t,
                traces=len(b),
                errors=sum(1 for s in b if s.status == "error"),
                tokens=sum(s.tokens_in + s.tokens_out for s in b),
                p95_ms=_percentile([s.duration_ms for s in b], 0.95),
            )
            for t, b in sorted(buckets.items())
        ]
        return stats

    async def list_apps(self) -> list[AppUsage]:
        apps: dict[str, AppUsage] = {}
        for s in self._summaries():
            a = apps.setdefault(s.app, AppUsage(app=s.app, traces=0, errors=0, last_seen_ns=0))
            a.traces += 1
            a.errors += 1 if s.status == "error" else 0
            a.last_seen_ns = max(a.last_seen_ns, s.start_ns)
        return sorted(apps.values(), key=lambda a: a.last_seen_ns, reverse=True)

    async def ping(self) -> bool:
        return True


# ---------------------------------------------------------------------------------------------
# ClickHouse store
# ---------------------------------------------------------------------------------------------

_PER_TRACE = """
    SELECT trace_id,
           any(app)                                            AS app,
           argMin(name, start_ns)                              AS root_name,
           min(start_ns)                                       AS start_ns,
           max(end_ns)                                         AS end_ns,
           (max(end_ns) - min(start_ns)) / 1e6                 AS duration_ms,
           count()                                             AS span_count,
           countIf(kind = 'llm')                               AS llm_calls,
           countIf(kind = 'tool')                              AS tool_calls,
           countIf(kind = 'retrieval')                         AS retrievals,
           countIf(status = 'error')                           AS errors,
           sum(tokens_in)                                      AS tokens_in,
           sum(tokens_out)                                     AS tokens_out,
           arraySort(groupUniqArrayIf(model, kind = 'llm'))    AS models,
           arraySort(groupUniqArrayIf(provider, kind = 'llm')) AS providers,
           if(countIf(status = 'error') > 0, 'error', 'ok')    AS status,
           argMinIf(input_preview, start_ns, input_preview != '')  AS input_preview,
           argMaxIf(output_preview, start_ns, output_preview != '') AS output_preview,
           countIf(notEmpty(truncated_attributes)) > 0         AS truncated,
           anyIf(run_id, run_id != '')                         AS run_id,
           anyIf(session_id, session_id != '')                 AS session_id
    FROM spans
    {where}
    GROUP BY trace_id
"""


class ClickHouseSpanStore:
    def __init__(self, settings: Settings) -> None:
        import clickhouse_connect

        self._client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
            secure=settings.clickhouse_secure,
        )
        self._db = settings.clickhouse_database

    def run_migrations(self) -> list[str]:
        return run_migrations(self._client, self._db)

    async def _query(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = await asyncio.to_thread(self._client.query, sql, parameters=params)
        return list(result.named_results())

    async def insert_spans(self, spans: Sequence[Span]) -> int:
        if not spans:
            return 0
        rows = [span_to_row(s, normalize.app_of(s)) for s in spans]
        await asyncio.to_thread(self._client.insert, "spans", rows, column_names=list(COLUMNS))
        return len(rows)

    async def get_trace(self, trace_id: str) -> list[Span]:
        rows = await self._query(
            "SELECT * FROM spans WHERE trace_id = {tid:String} ORDER BY start_ns, span_id",
            {"tid": trace_id},
        )
        return [row_to_span(r) for r in rows]

    @staticmethod
    def _span_where(
        app: str | None, since_ns: int | None, until_ns: int | None
    ) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if app:
            clauses.append("app = {app:String}")
            params["app"] = app
        if since_ns is not None:
            clauses.append("start_ns >= {since:Int64}")
            params["since"] = since_ns
        if until_ns is not None:
            clauses.append("start_ns <= {until:Int64}")
            params["until"] = until_ns
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

    async def list_traces(self, flt: TraceFilter) -> TracePage:
        where, params = self._span_where(flt.app, flt.since_ns, flt.until_ns)
        having: list[str] = []
        if flt.status:
            having.append("status = {status:String}")
            params["status"] = flt.status
        if flt.model:
            having.append("has(models, {model:String})")
            params["model"] = flt.model
        if flt.provider:
            having.append("has(providers, {provider:String})")
            params["provider"] = flt.provider
        if flt.min_duration_ms is not None:
            having.append("duration_ms >= {min_d:Float64}")
            params["min_d"] = flt.min_duration_ms
        if flt.max_duration_ms is not None:
            having.append("duration_ms <= {max_d:Float64}")
            params["max_d"] = flt.max_duration_ms
        if flt.has_tools is not None:
            having.append("tool_calls > 0" if flt.has_tools else "tool_calls = 0")
        if flt.has_retrievals is not None:
            having.append("retrievals > 0" if flt.has_retrievals else "retrievals = 0")
        if flt.kind in ("llm", "tool", "retrieval"):
            having.append(f"{flt.kind}_calls > 0" if flt.kind != "retrieval" else "retrievals > 0")
        if flt.q:
            having.append(
                "(positionCaseInsensitive(root_name, {q:String}) > 0"
                " OR startsWith(trace_id, {q:String})"
                " OR positionCaseInsensitive(input_preview, {q:String}) > 0"
                " OR positionCaseInsensitive(output_preview, {q:String}) > 0"
                " OR run_id = {q:String})"
            )
            params["q"] = flt.q
        order = {
            "start_asc": "start_ns ASC",
            "duration_desc": "duration_ms DESC",
            "tokens_desc": "(tokens_in + tokens_out) DESC",
        }.get(flt.sort, "start_ns DESC")
        having_sql = ("HAVING " + " AND ".join(having)) if having else ""
        base = _PER_TRACE.format(where=where) + " " + having_sql
        params.update({"limit": flt.limit, "offset": flt.offset})
        rows, total = await asyncio.gather(
            self._query(
                f"{base} ORDER BY {order} LIMIT {{limit:UInt32}} OFFSET {{offset:UInt32}}", params
            ),
            self._query(f"SELECT count() AS n FROM ({base})", params),
        )
        return TracePage(
            items=[
                TraceSummary(
                    **{
                        **r,
                        "run_id": r["run_id"] or None,
                        "session_id": r["session_id"] or None,
                        "input_preview": r["input_preview"] or None,
                        "output_preview": r["output_preview"] or None,
                        "truncated": bool(r["truncated"]),
                    }
                )
                for r in rows
            ],
            total=int(total[0]["n"]) if total else 0,
            limit=flt.limit,
            offset=flt.offset,
        )

    async def overview(
        self, *, app: str | None, since_ns: int, until_ns: int, bucket_ns: int
    ) -> OverviewStats:
        where, params = self._span_where(app, since_ns, until_ns)
        per_trace = _PER_TRACE.format(where=where)
        params["bucket"] = bucket_ns
        totals, kinds, models, apps, series = await asyncio.gather(
            self._query(
                f"""SELECT count() AS traces, countIf(status = 'error') AS errors,
                           sum(span_count) AS spans, sum(tokens_in) AS tokens_in,
                           sum(tokens_out) AS tokens_out,
                           quantile(0.5)(duration_ms) AS p50, quantile(0.95)(duration_ms) AS p95,
                           avg(duration_ms) AS avg_ms
                    FROM ({per_trace})""",
                params,
            ),
            self._query(f"SELECT kind, count() AS n FROM spans {where} GROUP BY kind", params),
            self._query(
                f"""SELECT model, provider, count() AS calls, sum(tokens_in) AS tokens_in,
                           sum(tokens_out) AS tokens_out
                    FROM spans {where + (" AND " if where else "WHERE ")} kind = 'llm'
                    GROUP BY model, provider ORDER BY calls DESC LIMIT 20""",
                params,
            ),
            self._query(
                f"""SELECT app, count() AS traces, countIf(status = 'error') AS errors,
                           max(start_ns) AS last_seen_ns
                    FROM ({per_trace}) GROUP BY app ORDER BY traces DESC""",
                params,
            ),
            self._query(
                f"""SELECT intDiv(start_ns, {{bucket:Int64}}) * {{bucket:Int64}} AS t_ns,
                           count() AS traces, countIf(status = 'error') AS errors,
                           sum(tokens_in + tokens_out) AS tokens,
                           quantile(0.95)(duration_ms) AS p95_ms
                    FROM ({per_trace}) GROUP BY t_ns ORDER BY t_ns""",
                params,
            ),
        )
        t = totals[0] if totals else {}
        by_kind = {r["kind"]: int(r["n"]) for r in kinds}
        traces = int(t.get("traces") or 0)
        return OverviewStats(
            since_ns=since_ns,
            until_ns=until_ns,
            bucket_ns=bucket_ns,
            traces=traces,
            spans=int(t.get("spans") or 0),
            llm_calls=by_kind.get("llm", 0),
            tool_calls=by_kind.get("tool", 0),
            retrievals=by_kind.get("retrieval", 0),
            errors=int(t.get("errors") or 0),
            error_rate=(int(t.get("errors") or 0) / traces) if traces else 0.0,
            tokens_in=int(t.get("tokens_in") or 0),
            tokens_out=int(t.get("tokens_out") or 0),
            p50_ms=float(t.get("p50") or 0.0),
            p95_ms=float(t.get("p95") or 0.0),
            avg_ms=float(t.get("avg_ms") or 0.0),
            by_kind=by_kind,
            by_model=[ModelUsage(**r) for r in models],
            by_app=[AppUsage(**r) for r in apps],
            series=[SeriesPoint(**r) for r in series],
        )

    async def list_apps(self) -> list[AppUsage]:
        rows = await self._query(
            f"""SELECT app, count() AS traces, countIf(status = 'error') AS errors,
                       max(start_ns) AS last_seen_ns
                FROM ({_PER_TRACE.format(where="")}) GROUP BY app ORDER BY last_seen_ns DESC""",
            {},
        )
        return [AppUsage(**r) for r in rows]

    async def ping(self) -> bool:
        try:
            await asyncio.to_thread(self._client.command, "SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False


def run_migrations(client: Any, database: str) -> list[str]:
    """Apply ``NNNN_*.sql`` files in order, tracking them in ``lens_migrations``."""
    client.command(f"CREATE DATABASE IF NOT EXISTS {database}")
    client.command(
        "CREATE TABLE IF NOT EXISTS lens_migrations "
        "(name String, applied_at DateTime DEFAULT now()) ENGINE = MergeTree ORDER BY name"
    )
    applied = {r[0] for r in client.query("SELECT name FROM lens_migrations").result_rows}
    done: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        for statement in re.split(r";\s*\n", path.read_text(encoding="utf-8")):
            if statement.strip():
                client.command(statement)
        client.insert("lens_migrations", [[path.name]], column_names=["name"])
        done.append(path.name)
    return done


def make_store(settings: Settings) -> SpanStore:
    if settings.span_store == "memory":
        return InMemorySpanStore()
    store = ClickHouseSpanStore(settings)
    store.run_migrations()
    return store
