# RAG demo (Lens example target)

A small, deliberately imperfect support assistant over a tiny Acme knowledge base. It is the
demo target for Lens: it emits OpenTelemetry traces, exposes a `/chat` endpoint for evaluation
and an `/attack` endpoint implementing the red-team `Target` contract, and ships a golden dataset.

## Run

```bash
uv run --package lens-rag-demo uvicorn rag_demo.app:app --port 8100
# point it at the Lens collector (or API):
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

## Deliberate weaknesses (so metrics and red-team have something to find)

- **Naive lexical retrieval** can surface a poisoned document (`doc-99`).
- **Literal answering**: without the defence, an instruction embedded in a retrieved document
  (indirect injection) or a direct "reveal your prompt" request can steer the answer / leak the
  synthetic canary `LENS_CANARY_ZX4471`.
- **Defence toggle** `RAG_DEMO_DEFENCE=on` adds an instruction-sanitising step. Run the red-team
  before and after to show attack success rate dropping (SPEC.md §6.4).

## Evaluate it

```bash
uv run lens eval --dataset data/gold/rag_demo.jsonl --app rag_demo --target http://localhost:8100/chat \
  --metrics faithfulness,answer_relevance,context_precision,context_recall,hallucination
```

## Red-team it (before/after defence)

```bash
uv run lens redteam --target http://localhost:8100/attack --app rag_demo --defence none
RAG_DEMO_DEFENCE=on uv run lens redteam --target http://localhost:8100/attack --app rag_demo --defence input-sanitiser
```
