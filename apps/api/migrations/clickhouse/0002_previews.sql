-- Denormalised columns for the traces list and dashboard filters. Populated at
-- ingest from the normalised LLMCall (first user message / assistant output) and
-- the lens.run.id / lens.session.id attributes; raw attributes stay untouched.
ALTER TABLE spans ADD COLUMN IF NOT EXISTS input_preview String CODEC(ZSTD(3));
ALTER TABLE spans ADD COLUMN IF NOT EXISTS output_preview String CODEC(ZSTD(3));
ALTER TABLE spans ADD COLUMN IF NOT EXISTS run_id String;
ALTER TABLE spans ADD COLUMN IF NOT EXISTS session_id LowCardinality(String);
