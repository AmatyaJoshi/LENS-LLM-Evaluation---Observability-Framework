# Lens — LLM Evaluation & Observability Framework

Lens is an open-source observability and evaluation platform for LLM applications and agents.
It ingests OpenTelemetry traces (OpenLLMetry / OTel GenAI semantic conventions) from any app,
reconstructs full agent trajectories, and runs a pluggable evaluation engine that scores each
trace for **faithfulness, answer relevance, context precision/recall, hallucination, tool-call
correctness, and trajectory efficiency**. A red-teaming module attacks the instrumented app with
150+ prompt-injection, jailbreak and data-exfiltration probes and reports attack success rate
over time. Judges are calibrated against human labels; a distilled small judge and a fine-tuned
prompt-injection detector are trained to replace frontier-model judging at scale. Regressions
gate CI via a GitHub Action, and an AI Assistant answers questions grounded in your Lens data.

**Why it is not a toy:** anyone can call an LLM-as-judge. Lens (a) measures how good the judge
itself is against human labels (Cohen's κ, Krippendorff's α, Spearman ρ, calibration), (b) trains
cheaper judges and reports the accuracy/cost trade-off honestly, and (c) treats security
evaluation as a first-class metric.

See [SPEC.md](SPEC.md) for the full architecture and the phased plan.

## What's built

| Area | Status |
|---|---|
| Ingest + normalise (OTLP/HTTP+protobuf, semconv contract, ClickHouse, trajectory reconstruction) | done |
| Dashboard (overview, traces, trace detail, trajectory graph, live feed, command palette) | done |
| Evaluation engine (10 metrics, judge router, cassette tests, agreement, calibration) | done |
| Datasets, eval runs with provenance, judge quality, labelling queue | done |
| Red team (150 seed probes → 1,200 with mutators, targets, ASR scoring, live detection) | done |
| AI Assistant (grounded in your Lens data) | done |
| Training pipelines (injection detector, distilled judge) — code + datacards | done |
| SDKs (Python + TypeScript), `lens` CLI, GitHub Action | done |

## Quick start

```bash
docker compose up -d --wait      # clickhouse, postgres, redis, otel-collector, api, worker, web
open http://localhost:3000       # dashboard

# replay a recorded trace, or point any OTel app at localhost:4318
uv run lens ingest tests/fixtures/otlp/openllmetry_python.json --endpoint http://localhost:8000
```

No Docker (works without WSL): `LENS_SPAN_STORE=memory uv run lens serve` in one terminal and
`cd apps/web && npm run dev` in another.

## Run the demo end to end

```bash
# 1. start the demo app (a deliberately imperfect RAG assistant) and point it at Lens
uv run --package lens-rag-demo uvicorn rag_demo.app:app --port 8100
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# 2. evaluate it on the golden set
uv run lens eval --dataset data/gold/rag_demo.jsonl --app rag_demo --target http://localhost:8100/chat

# 3. red-team it, before and after a defence
uv run lens redteam --target http://localhost:8100/attack --app rag_demo --defence none
RAG_DEMO_DEFENCE=on uv run lens redteam --target http://localhost:8100/attack --app rag_demo --defence input-sanitiser
```

## `lens` CLI

`ingest` · `serve` · `eval` (offline scoring over a dataset) · `ci` (regression gate with a
markdown summary) · `redteam` (attack a target, report ASR) · `label` (terminal labelling from
the disagreement queue).

## Repository layout

| Path | What |
|---|---|
| `packages/lens-core` | trace model, trajectory reconstruction, metrics, judges, red team, datasets, `lens` CLI |
| `apps/api` | FastAPI: OTLP ingest, semconv contract, ClickHouse + Postgres, evals/judges/labels/redteam/assistant |
| `apps/worker` | Celery tasks (online eval, dataset eval, red team) |
| `apps/collector` | OpenTelemetry Collector config |
| `apps/web` | Next.js 15 dashboard + AI Assistant |
| `packages/lens-sdk-python`, `packages/lens-sdk-ts` | thin OTel/OpenLLMetry wrappers with Lens helpers |
| `packages/lens-ci-action` | composite GitHub Action that gates CI on metric regressions |
| `training/injection`, `training/judge` | detector + distilled-judge pipelines (build → train → eval → export) |
| `examples/rag_demo` | instrumented demo app with deliberate weaknesses |
| `data/probes`, `data/gold` | attack corpus (150 probes) and the RAG demo golden set |

## Metrics

Every built-in metric documents its formula in its docstring and is unit-tested against recorded
judge cassettes (no live LLM in tests):

- **Faithfulness** — fraction of atomic claims in the answer supported by the retrieved context.
- **Answer relevance** — generated-question embedding similarity blended with a rubric grade.
- **Context precision / recall** — rank-weighted usefulness of retrieved chunks; reference-answer
  sentences attributable to the context.
- **Hallucination** — weighted share of contradicted (1.0) and unverifiable (0.5) claims.
- **Tool-call correctness** — right tool, valid + semantically right args, result used in the answer.
- **Trajectory efficiency** — steps vs a reference minimum, penalised for redundancy and loops.
- **Task completion / Safety / Calibration** — rubric + order-swapped pairwise; detector + judge;
  Brier score of stated confidence vs outcome.

## Judges and their quality

Judges route across tiers (`frontier` Claude, `second_opinion` OpenAI, `local` distilled model on
vLLM, `nli` DeBERTa). Every prompt is versioned and every `Score` records the prompt version, judge
model, cost and latency. The Judge Quality page reports κ / α / ρ against a human gold set and
between judges, plus cost per 1k evaluations — so you can see whether a judge is trustworthy before
you trust it.

## Security

The injection detector scans every untrusted text segment at ingest (user/tool messages, retrieved
documents, tool results) and stamps `lens.security.*` attributes; flagged traffic surfaces on the
Security page. The red-team suite defines success only as a policy violation of your own target
(a leaked canary, a forbidden tool call, an exfiltration URL), never as producing harmful content.

## Training

Both pipelines follow the same convention (`build_*` → `train_*` → `eval_*` → `export_*`) and write
datacards. **No metric number appears in this README unless it points to a results file in
`training/results/`** (see CLAUDE.md). None are claimed until the pipelines are run — see
[`training/README.md`](training/README.md) and the model cards in `training/MODEL_CARDS/`.

## Development

```bash
uv sync
uv run pytest -q                                  # 114 tests, all offline
uv run ruff check . && uv run ruff format --check . && uv run mypy
cd apps/web && npm ci && npm run build
```

## Semantic-convention contract

Lens accepts OTel GenAI (`gen_ai.*`), OpenLLMetry (`llm.*`, `traceloop.*`) and Lens (`lens.*`)
attributes and normalises them to one model (SPEC.md §4, implemented attribute-by-attribute in
`apps/api/lens_api/ingest/semconv.py`). The conformance suite proves four differently-instrumented
recordings of the same run produce a byte-identical `Trajectory`.
