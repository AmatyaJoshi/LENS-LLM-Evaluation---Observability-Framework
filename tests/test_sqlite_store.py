"""SQLite span store: persistence across restarts + cost accounting in summaries."""

from __future__ import annotations

import asyncio
from pathlib import Path

from lens_api.ingest import normalize
from lens_api.models.clickhouse import SqliteSpanStore, TraceFilter
from tests.conftest import load_fixture

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


def test_persists_across_restart_and_reports_cost(tmp_path: Path) -> None:
    db = str(tmp_path / "spans.db")
    spans = normalize.otlp_json_to_spans(load_fixture("openllmetry_python"))

    async def go() -> None:
        store = SqliteSpanStore(db)
        await store.insert_spans(spans)
        page = await store.list_traces(TraceFilter())
        assert page.total == 1
        t = page.items[0]
        assert t.tokens_in == 182 + 231 and t.cost_usd > 0  # gpt-4o-mini is priced
        # simulate a restart: a brand-new store instance rebuilds from disk
        store2 = SqliteSpanStore(db)
        page2 = await store2.list_traces(TraceFilter())
        assert page2.total == 1 and page2.items[0].trace_id == TRACE_ID
        assert len(await store2.get_trace(TRACE_ID)) == 5
        stats = await store2.overview(app=None, since_ns=0, until_ns=10**19, bucket_ns=10**9)
        assert stats.traces == 1 and stats.cost_usd > 0

    asyncio.run(go())


def test_upsert_is_idempotent(tmp_path: Path) -> None:
    db = str(tmp_path / "spans.db")
    spans = normalize.otlp_json_to_spans(load_fixture("lens_sdk"))

    async def go() -> None:
        store = SqliteSpanStore(db)
        await store.insert_spans(spans)
        await store.insert_spans(spans)  # same batch again
        store2 = SqliteSpanStore(db)
        assert (await store2.list_traces(TraceFilter())).total == 1

    asyncio.run(go())
