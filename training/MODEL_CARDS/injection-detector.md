# Model card: lens-injection-detector

**Task:** binary prompt-injection / jailbreak detection over a text segment (user message,
retrieved document, or tool result). SPEC.md §7.2.

**Architecture:** `microsoft/deberta-v3-base` sequence classifier (a `deberta-v3-xsmall`
variant is available for latency, and a `ModernBERT-base` variant via `--model`). Exported to
ONNX with int8 dynamic quantisation; served in the Lens ingest path via `LENS_DETECTOR_PATH`.

**Training data:** `training/injection/build_dataset.py` — Lens probe corpus + deterministic
mutators and public injection/jailbreak sets as positives; benign chat plus **hard negatives**
(text discussing instructions, code/comments) as negatives.

**Intended use:** flag untrusted text at ingest and gate the safety metric. Not a content
moderation classifier; it detects *instructions that try to override the operator*, not toxicity.

**Evaluation:** `eval_detector.py` reports per-source F1/AUROC, hard-negative FPR, held-out
mutator robustness, and CPU p50/p95 latency. **Numbers live in `training/results/` and are cited
in the README only from there (CLAUDE.md).** No numbers are claimed until the pipeline is run.

**Limitations:** public benchmarks are easy and inflate F1; the held-out-mutator and
hard-negative metrics are the honest signal. A heuristic detector is the always-available
fallback when no trained model is present.
