# Changelog

All notable changes to Lens. Format loosely follows Keep a Changelog; this is
pre-1.0 so surfaces may still move.

## [Unreleased]

### Added
- Phases 0–8 (SPEC.md §10): OTLP ingest + semconv normalisation, trajectory
  reconstruction, ClickHouse/Postgres/SQLite stores, Next.js dashboard, the
  evaluation engine (10 metrics), judge router + agreement + calibration,
  datasets/eval-runs/labelling, the 150-probe red-team suite with mutators and
  live injection detection, training pipelines (detector + distilled judge),
  Python/TS SDKs, and the `lens-ci-action` regression gate.
- AI Assistant grounded in the operator's own Lens data (OpenRouter-compatible).
- Persistent SQLite span store (`LENS_SPAN_STORE=sqlite`) — no Docker required.
- Cost accounting via a model price table (`lens_core.pricing`).
- Red-team LLM mutators (paraphrase, translate).
- Request guards: body-size cap, per-key/IP rate limiting, multi-key auth.

### Notes
- Model/detector metric numbers are intentionally absent until the training
  pipelines are run and write result files (see CLAUDE.md).
