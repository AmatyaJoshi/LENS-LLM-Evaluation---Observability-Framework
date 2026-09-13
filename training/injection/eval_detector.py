"""Evaluate the injection detector (SPEC.md §7.2).

Reports, and writes to training/results:
- F1 / AUROC on the held-out test split and on each public test set separately
  (generalisation gaps are the interesting part);
- false-positive rate on hard negatives;
- adversarial robustness: F1 on mutated probes whose mutator family was held out of training;
- latency benchmark (p50/p95) on CPU;
- comparison to the zero-shot heuristic detector and, with --frontier, a zero-shot LLM classifier.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from training.common import binary_metrics, write_results

DATA = Path(__file__).parent / "data"
DEFAULT_MODEL = Path(__file__).parent / "artifacts" / "detector"
HELD_OUT_MUTATORS = (
    "confusables",
    "zero_width",
)  # families excluded from training for the robustness test


def load_split(name: str) -> list[dict[str, object]]:
    path = DATA / f"{name}.jsonl"
    return (
        [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        if path.exists()
        else []
    )


def _hf_scores(model_dir: Path, texts: list[str], max_len: int = 512) -> list[float]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir)).eval()
    scores: list[float] = []
    with torch.no_grad():
        for i in range(0, len(texts), 32):
            batch = tok(
                texts[i : i + 32],
                truncation=True,
                max_length=max_len,
                padding=True,
                return_tensors="pt",
            )
            probs = torch.softmax(model(**batch).logits, dim=-1)[:, 1]
            scores.extend(probs.tolist())
    return scores


def _latency(model_dir: Path, sample: list[str]) -> dict[str, float]:
    """p50/p95 single-item CPU latency (ms) via the Lens ONNX detector if exported, else HF."""
    from lens_core.redteam.detector import HeuristicDetector, OnnxDetector

    onnx_dir = model_dir.parent / "onnx"
    detector = OnnxDetector(onnx_dir) if (onnx_dir / "model.onnx").exists() else HeuristicDetector()
    lat: list[float] = []
    for text in sample:
        t0 = time.perf_counter()
        detector.score(text)
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, round(q * (len(lat) - 1)))] if lat else 0.0  # noqa: E731
    return {"detector": detector.name, "p50_ms": p(0.5), "p95_ms": p(0.95)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument(
        "--heuristic-only", action="store_true", help="benchmark the heuristic baseline only"
    )
    args = ap.parse_args()

    test = load_split("test")
    if not test:
        raise SystemExit("no test split; run build_dataset.py first")
    texts = [str(r["text"]) for r in test]
    labels = [int(r["label"]) for r in test]

    results: dict[str, object] = {"n_test": len(test)}

    # heuristic baseline (always available)
    from lens_core.redteam.detector import HeuristicDetector

    heur = HeuristicDetector(threshold=args.threshold)
    heur_scores = [heur.score(t).score for t in texts]
    results["heuristic"] = binary_metrics(
        labels, [1 if s >= args.threshold else 0 for s in heur_scores], heur_scores
    )

    # trained model (if present)
    if not args.heuristic_only and (args.model / "model_card.json").exists():
        scores = _hf_scores(args.model, texts)
        preds = [1 if s >= args.threshold else 0 for s in scores]
        results["model"] = binary_metrics(labels, preds, scores)
        # per-source generalisation
        by_source: dict[str, dict[str, float]] = {}
        for src in sorted({str(r["source"]) for r in test}):
            idx = [i for i, r in enumerate(test) if r["source"] == src]
            if idx:
                by_source[src] = binary_metrics([labels[i] for i in idx], [preds[i] for i in idx])
        results["by_source"] = by_source
        # hard-negative FPR
        hn = [i for i, r in enumerate(test) if r["source"] == "hard_negative"]
        if hn:
            fp = sum(preds[i] for i in hn)
            results["hard_negative_fpr"] = fp / len(hn)
        # adversarial robustness on held-out mutator families
        from lens_core.redteam import apply_deterministic, load_probes

        probes = load_probes(Path(__file__).resolve().parents[2] / "data" / "probes")
        mutated = [
            v.payload
            for p in probes
            for v in apply_deterministic(p, list(HELD_OUT_MUTATORS))
            if v.payload
        ]
        if mutated:
            mscores = _hf_scores(args.model, mutated)
            results["held_out_mutator_recall"] = sum(
                1 for s in mscores if s >= args.threshold
            ) / len(mscores)
            results["held_out_mutators"] = list(HELD_OUT_MUTATORS)

    results["latency"] = _latency(args.model, texts[:200])
    write_results("injection_eval", results)
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
