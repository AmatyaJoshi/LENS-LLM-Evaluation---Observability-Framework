# lens-ci-action

A composite GitHub Action that runs Lens evaluations on a dataset and **fails the build when a
metric regresses** beyond a threshold (SPEC.md §5.4, §9). It posts a markdown table as a PR
comment and to the job summary, and uploads the full results JSON.

## Usage

```yaml
# .github/workflows/eval.yml
name: eval
on: pull_request
jobs:
  lens:
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: AmatyaJoshi/lens/packages/lens-ci-action@v1
        with:
          dataset: data/gold/rag_demo.jsonl        # or a dataset name in your Lens API
          app: rag_demo
          app_command: "uv run --package lens-rag-demo uvicorn rag_demo.app:app --port 8100"
          target: http://localhost:8100/chat
          thresholds: "faithfulness:-0.03,hallucination:+0.02"
          baseline: latest
```

### Offline mode (no Lens API)

Point `baseline_file` at a results JSON produced by a previous `lens eval --out`, and omit
`endpoint`. The gate compares the current run to that file and never needs a server.

## Inputs

See [`action.yml`](action.yml). Key ones: `dataset`, `app`, `target` / `app_command`,
`thresholds`, `baseline` (or `baseline_file`), `metrics`, `judge`, `endpoint`, `api_key`.

## Exit behaviour

- Exit `0` and a ✅ summary when no metric regresses.
- Exit `1` and a ❌ summary naming the regressed metrics otherwise.

A negative threshold is the allowed *drop* for a higher-is-better metric; a positive threshold
is the allowed *rise* for a lower-is-better metric (e.g. `hallucination:+0.02`). Metrics without
an explicit threshold get a ±0.02 tolerance in the appropriate direction.
