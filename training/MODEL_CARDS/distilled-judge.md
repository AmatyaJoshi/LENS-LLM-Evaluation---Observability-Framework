# Model card: lens-judge-small (distilled faithfulness/hallucination judge)

**Task:** given (question, contexts, answer), label each atomic claim
supported/contradicted/unverifiable and output an overall faithfulness score in [0,1]. SPEC.md §7.1.

**Architecture:** `Qwen2.5-3B-Instruct` + LoRA (r=16, α=32) SFT to an instruction→JSON format
(`train_judge_lora.py`); a `deberta-v3-large` 3-way NLI baseline (`train_deberta_nli.py`) is
trained alongside because it is expected to win on cost — `eval_judge.py` reports that honestly.
Merged weights are served on vLLM as `lens-judge-small` (router `local` tier).

**Training data:** `build_distill_set.py` — public labelled sets (HaluEval, RAGTruth, FEVER/
VitaminC) plus frontier-judge distillation over RAG demo / Sentinel triples, split by source
document to avoid leakage. The human gold set is merged at eval time only.

**Evaluation:** `eval_judge.py` reports per-class F1, AUROC on the overall score, κ vs humans and
vs the frontier judge, and cost/latency per 1k evals — with an accuracy-vs-cost Pareto plot.
**All numbers live in `training/results/`.** Target (SPEC.md §1.3): within 5 F1 of the frontier
judge at ≥ 20× lower cost — reported honestly, not assumed.

**Limitations:** distilled from a frontier judge, so it inherits that judge's biases; the
DeBERTa NLI variant does not produce free-text rationales.
