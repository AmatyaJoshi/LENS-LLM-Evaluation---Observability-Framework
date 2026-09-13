# Lens: LLM Evaluation & Observability Framework

Lens is an open-source observability and evaluation platform for LLM applications and agents.
It ingests OpenTelemetry traces (OpenLLMetry / OTel GenAI semantic conventions) from any app,
reconstructs full agent trajectories, and runs a pluggable evaluation engine that scores each
trace for faithfulness, answer relevance, context precision/recall, hallucination, tool-call
correctness, and trajectory efficiency. A red-teaming module continuously attacks the
instrumented app and reports attack success rate over time. Judges are calibrated against
human labels; a distilled small judge and a fine-tuned prompt-injection detector replace
frontier-model judging at scale. Regressions gate CI via a GitHub Action.

See [SPEC.md](SPEC.md) for the full architecture and phased plan. Status: **Phase 1** (ingest
and normalise) is implemented; phases 2 to 8 follow the plan in SPEC.md §10.

## Quick start

```bash
docker compose up -d --wait          # clickhouse, postgres, redis, otel-collector, api, worker, web
curl -s localhost:8000/health

# send a recorded trace (OTLP/JSON) through the collector...
curl -X POST localhost:4318/v1/traces -H 'content-type: application/json' \
     --data @tests/fixtures/otlp/openllmetry_python.json
# ...or straight to the API with the CLI
uv run lens ingest tests/fixtures/otlp/otel_genai.json --endpoint http://localhost:8000

curl -s localhost:8000/traces | jq
curl -s localhost:8000/traces/0af7651916cd43dd8448eb211c80319c/trajectory | jq
```

Point any OpenLLMetry / OTel-instrumented app at `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`.

## Development

```bash
uv sync                      # Python 3.12 workspace: lens-core, lens-api, lens-worker, lens-sdk
uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run mypy
cd apps/web && npm ci && npm run dev
```

`LENS_SPAN_STORE=memory uv run lens serve` runs the API without ClickHouse.

## Repository layout

| Path | What |
|---|---|
| `packages/lens-core` | normalised trace model, trajectory reconstruction, `lens` CLI; later: metrics, judges, red team |
| `apps/api` | FastAPI: OTLP/HTTP ingest, semconv contract (`ingest/semconv.py`), ClickHouse + Postgres models, REST + WebSocket |
| `apps/worker` | Celery tasks |
| `apps/collector` | OpenTelemetry Collector config (OTLP gRPC + HTTP in, Lens API out) |
| `apps/web` | Next.js 15 dashboard |
| `tests/fixtures/otlp` | conformance fixtures: the same logical run recorded in four conventions |

## Semantic-convention contract

Lens accepts OTel GenAI (`gen_ai.*`), OpenLLMetry (`llm.*`, `traceloop.*`) and Lens (`lens.*`)
attributes and normalises them to one model. The mapping table is SPEC.md §4 and is implemented,
attribute name by attribute name, in `apps/api/lens_api/ingest/semconv.py`. The conformance suite
(`tests/test_conformance.py`) asserts that four differently-instrumented recordings of the same run
produce byte-identical `Trajectory` objects.

## Red-teaming scope and ethics

Probes target the user's own application, contain no harmful how-to content, and define success
as a policy violation of the target (for example "leaked system prompt"), never as the production
of dangerous content.

## Metric numbers

No metric number appears in this README unless it points to a results file under
`training/results/` or a benchmark output. None yet.
