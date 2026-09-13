-- Lens span store (SPEC.md §2.1, §3.1). One row per span; wide columns for the
-- hot filters, raw attributes/events preserved as JSON strings (never dropped).
CREATE TABLE IF NOT EXISTS spans
(
    trace_id             String,
    span_id              String,
    parent_span_id       String,
    app                  LowCardinality(String),
    name                 String,
    kind                 LowCardinality(String),
    start_ns             Int64,
    end_ns               Int64,
    duration_ms          Float64,
    status               LowCardinality(String),
    status_message       String,
    provider             LowCardinality(String),
    model                LowCardinality(String),
    tokens_in            UInt32,
    tokens_out           UInt32,
    attributes           String CODEC(ZSTD(3)),
    resource             String CODEC(ZSTD(3)),
    events               String CODEC(ZSTD(3)),
    truncated_attributes Array(String),
    ingested_at          DateTime64(3) DEFAULT now64(3),
    start_time           DateTime64(9) MATERIALIZED fromUnixTimestamp64Nano(start_ns)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(start_time)
ORDER BY (app, start_ns, trace_id, span_id)
TTL toDateTime(start_time) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- Secondary index for point lookups by trace (ORDER BY leads with app).
ALTER TABLE spans ADD INDEX IF NOT EXISTS idx_trace_id trace_id TYPE bloom_filter GRANULARITY 4;
