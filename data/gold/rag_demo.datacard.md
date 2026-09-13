# RAG demo golden set

- Examples: 58
- Breakdown: {'answerable': 50, 'out_of_scope': 5, 'adversarial': 3}
- Split: all `test` (offline eval / CI gate).
- Built deterministically by `data/gold/build_rag_demo_gold.py`.
- Answerable items carry the source document id in metadata for leakage-free splitting.
- Out-of-scope and adversarial items expect a graceful refusal, exercising relevance,
  hallucination and safety metrics.
