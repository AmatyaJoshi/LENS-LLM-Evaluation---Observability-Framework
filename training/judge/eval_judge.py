"""Evaluate the distilled judges against the frontier judge and human gold (SPEC.md §7.1).

Reports, and writes to training/results (so README numbers are traceable):
- F1 per class and AUROC on the overall faithfulness score, on the held-out test split;
- Cohen's κ vs humans and vs the frontier judge;
- cost per 1k evaluations and p95 latency for frontier vs distilled LoRA vs DeBERTa;
- a Pareto accuracy-vs-cost table (and a plot when matplotlib is present).

Judges are compared through the same Lens ``Judge`` interface, so this is an apples-to-apples
comparison. Distilled/local judges are reached via vLLM (OpenAI-compatible) using the router's
``local`` tier; the DeBERTa NLI judge scores (claim, context) pairs directly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lens_core.judges.agreement import binarize, cohen_kappa
from training.common import auroc, binary_metrics, write_results

DATA = Path(__file__).parent / "data"


def load_test() -> list[dict[str, object]]:
    path = DATA / "test.jsonl"
    if not path.exists():
        raise SystemExit("no test split; run build_distill_set.py first")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


async def _score_with_judge(
    tier: str, rows: list[dict[str, object]]
) -> tuple[list[float], float, float]:
    """Return (faithfulness scores, cost_usd, p95_latency_ms) for a router tier."""
    from lens_core.judges.router import JudgeRouter
    from lens_core.metrics import EvalItem, get_metric

    judge = JudgeRouter.from_env().get(tier)
    faith = get_metric("faithfulness")
    scores: list[float] = []
    for r in rows:
        item = EvalItem(
            input=str(r["question"]), output=str(r["answer"]), contexts=list(r["contexts"])
        )  # type: ignore[arg-type]
        result = await faith.score(item, judge)
        scores.append(result.value)
    return scores, judge.stats.cost_usd, judge.stats.p95_latency_ms


def main() -> None:
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default="frontier,local", help="router tiers to compare")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()

    rows = load_test()
    gold = [float(r["faithfulness"]) for r in rows]  # distillation/gold target scores
    gold_bin = binarize(gold, args.threshold)

    results: dict[str, object] = {"n_test": len(rows), "judges": {}}
    frontier_scores: list[float] | None = None
    pareto: list[dict[str, object]] = []

    for tier in [t.strip() for t in args.tiers.split(",") if t.strip()]:
        try:
            scores, cost, p95 = asyncio.run(_score_with_judge(tier, rows))
        except Exception as exc:  # noqa: BLE001
            results["judges"][tier] = {"error": str(exc)}  # type: ignore[index]
            continue
        preds = binarize(scores, args.threshold)
        entry = {
            "binary": binary_metrics(gold_bin, preds, scores),
            "auroc_vs_gold": auroc(gold_bin, scores),
            "kappa_vs_gold": cohen_kappa(gold_bin, preds),
            "cost_per_1k_usd": round(cost / max(len(rows), 1) * 1000, 4),
            "p95_latency_ms": round(p95, 1),
        }
        if tier == "frontier":
            frontier_scores = scores
        elif frontier_scores is not None:
            entry["kappa_vs_frontier"] = cohen_kappa(
                binarize(frontier_scores, args.threshold), preds
            )
        results["judges"][tier] = entry  # type: ignore[index]
        pareto.append(
            {
                "judge": tier,
                "f1": entry["binary"]["f1"],
                "cost_per_1k_usd": entry["cost_per_1k_usd"],
            }
        )

    results["pareto"] = pareto
    # honest cost-vs-accuracy delta vs frontier (SPEC.md §1.3 definition of done)
    if "frontier" in results["judges"] and isinstance(results["judges"]["frontier"], dict):  # type: ignore[index]
        f = results["judges"]["frontier"]  # type: ignore[index]
        for tier, entry in results["judges"].items():  # type: ignore[union-attr]
            if (
                tier != "frontier"
                and isinstance(entry, dict)
                and "binary" in entry
                and f.get("cost_per_1k_usd")
            ):
                entry["f1_delta_vs_frontier"] = round(entry["binary"]["f1"] - f["binary"]["f1"], 4)
                if entry["cost_per_1k_usd"]:
                    entry["cost_ratio_vs_frontier"] = round(
                        f["cost_per_1k_usd"] / entry["cost_per_1k_usd"], 1
                    )

    path = write_results("judge_eval", results)

    if args.plot:
        try:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(5, 4))
            for p in pareto:
                ax.scatter(p["cost_per_1k_usd"], p["f1"], label=p["judge"])
                ax.annotate(str(p["judge"]), (p["cost_per_1k_usd"], p["f1"]))
            ax.set_xlabel("cost per 1k evals ($)")
            ax.set_ylabel("F1 vs gold")
            ax.set_title("Judge accuracy vs cost (Pareto)")
            ax.set_xscale("log")
            fig.tight_layout()
            fig.savefig(path.with_suffix(".png"), dpi=120)
            print(f"wrote plot -> {path.with_suffix('.png')}")
        except ImportError:
            pass

    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
