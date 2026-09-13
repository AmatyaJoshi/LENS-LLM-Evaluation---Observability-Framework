"""Span store: ClickHouse (production) and in-memory (tests / --lite dev).

Schema lives in ``apps/api/migrations/clickhouse/*.sql`` and is applied by
``run_migrations`` at API start-up; never hand-edit the live schema (CLAUDE.md).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from lens_api.ingest import normalize, semconv
from lens_api.settings import Settings
from lens_core.trace.model import Span, SpanEvent

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "clickhouse"

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
)


class TraceSummary(dict[str, Any]):
    """Row of the traces list: trace_id, app, root name, start, duration, span/llm counts."""


class SpanStore(Protocol):
    async def insert_spans(self, spans: Sequence[Span]) -> int: ...
    async def get_trace(self, trace_id: str) -> list[Span]: ...
    async def list_traces(
        self, *, app: str | None = None, limit: int = 50
    ) -> list[TraceSummary]: ...
    async def ping(self) -> bool: ...


def span_to_row(span: Span, app: str) -> list[Any]:
    tokens_in, tokens_out = semconv.tokens(span.attributes) if span.kind == "llm" else (0, 0)
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


def _summarise(trace_id: str, spans: Iterable[Span]) -> TraceSummary:
    spans = list(spans)
    by_id = {s.span_id: s for s in spans}
    roots = [s for s in spans if not s.parent_span_id or s.parent_span_id not in by_id]
    root = min(roots or spans, key=lambda s: s.start_ns)
    start = min(s.start_ns for s in spans)
    end = max(s.end_ns for s in spans)
    return TraceSummary(
        trace_id=trace_id,
        app=normalize.app_of(root),
        root_name=root.name,
        start_ns=start,
        duration_ms=(end - start) / 1_000_000,
        span_count=len(spans),
        llm_calls=sum(1 for s in spans if s.kind == "llm"),
        tool_calls=sum(1 for s in spans if s.kind == "tool"),
        status="error" if any(s.status == "error" for s in spans) else "ok",
    )


class InMemorySpanStore:
    def __init__(self) -> None:
        self._spans: dict[str, dict[str, Span]] = defaultdict(dict)

    async def insert_spans(self, spans: Sequence[Span]) -> int:
        for s in spans:
            self._spans[s.trace_id][s.span_id] = s
        return len(spans)

    async def get_trace(self, trace_id: str) -> list[Span]:
        return sorted(self._spans.get(trace_id, {}).values(), key=lambda s: (s.start_ns, s.span_id))

    async def list_traces(self, *, app: str | None = None, limit: int = 50) -> list[TraceSummary]:
        summaries = [_summarise(tid, spans.values()) for tid, spans in self._spans.items()]
        if app:
            summaries = [s for s in summaries if s["app"] == app]
        summaries.sort(key=lambda s: s["start_ns"], reverse=True)
        return summaries[:limit]

    async def ping(self) -> bool:
        return True


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

    async def insert_spans(self, spans: Sequence[Span]) -> int:
        if not spans:
            return 0
        rows = [span_to_row(s, normalize.app_of(s)) for s in spans]
        await asyncio.to_thread(self._client.insert, "spans", rows, column_names=list(COLUMNS))
        return len(rows)

    async def get_trace(self, trace_id: str) -> list[Span]:
        result = await asyncio.to_thread(
            self._client.query,
            "SELECT * FROM spans WHERE trace_id = {tid:String} ORDER BY start_ns, span_id",
            parameters={"tid": trace_id},
        )
        return [row_to_span(r) for r in result.named_results()]

    async def list_traces(self, *, app: str | None = None, limit: int = 50) -> list[TraceSummary]:
        where = "WHERE app = {app:String}" if app else ""
        sql = f"""
            SELECT trace_id, any(app) AS app,
                   argMin(name, start_ns) AS root_name,
                   min(start_ns) AS start_ns,
                   (max(end_ns) - min(start_ns)) / 1e6 AS duration_ms,
                   count() AS span_count,
                   countIf(kind = 'llm') AS llm_calls,
                   countIf(kind = 'tool') AS tool_calls,
                   if(countIf(status = 'error') > 0, 'error', 'ok') AS status
            FROM spans {where}
            GROUP BY trace_id ORDER BY start_ns DESC LIMIT {{limit:UInt32}}
        """
        result = await asyncio.to_thread(
            self._client.query, sql, parameters={"app": app or "", "limit": limit}
        )
        return [TraceSummary(**r) for r in result.named_results()]

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
