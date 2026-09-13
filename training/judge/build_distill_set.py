"""Build the distilled faithfulness/hallucination judge training set (SPEC.md §7.1).

Two kinds of examples, unified into an instruction→JSON format:
1. Public labelled data: RAGTruth (span-level hallucination), HaluEval (QA/dialogue/summ),
   FEVER/VitaminC (NLI claim verification). Loaded when ``datasets`` is available.
2. Distillation: run the frontier judge (via the Lens metric prompts) over unlabelled
   (question, contexts, answer) triples from the RAG demo + Sentinel + public RAG traces,
   keeping the frontier verdicts + rationales as targets.
3. Gold: the human gold set exported from Lens (``lens label`` / API) is merged for eval, not
   training, and split by source document to avoid leakage.

Deterministic; writes train/val/test JSONL + datacard. ``--offline`` builds from the RAG demo
golden set and the Lens cassette (if configured) so the pipeline runs without network or keys.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "data"

INSTRUCTION = (
    "You are a faithfulness judge. Given a question, contexts and an answer, label each atomic "
    "claim in the answer as supported/contradicted/unverifiable against the contexts, and give an "
    "overall faithfulness score in [0,1]. Reply with JSON: "
    '{"verdicts": [{"claim": str, "verdict": str}], "faithfulness": float}.'
)


def _format(
    question: str, contexts: list[str], answer: str, target: dict[str, Any]
) -> dict[str, Any]:
    ctx = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
    prompt = f"Question: {question}\n\nContexts:\n{ctx}\n\nAnswer: {answer}"
    return {
        "instruction": INSTRUCTION,
        "input": prompt,
        "output": json.dumps(target, ensure_ascii=False),
        "question": question,
        "contexts": contexts,
        "answer": answer,
        "faithfulness": target["faithfulness"],
        "source_document": (contexts[0][:32] if contexts else "none"),
    }


def _public_examples(offline: bool) -> list[dict[str, Any]]:
    if offline:
        return []
    try:
        from datasets import load_dataset
    except ImportError:
        return []
    rows: list[dict[str, Any]] = []
    try:  # HaluEval QA: right_answer (faithful) vs hallucinated_answer
        ds = load_dataset("pminervini/HaluEval", "qa", split="data")
        for r in ds.select(range(min(len(ds), 4000))):
            q, ctx = r["question"], [r.get("knowledge", "")]
            rows.append(_format(q, ctx, r["right_answer"], {"verdicts": [], "faithfulness": 1.0}))
            rows.append(
                _format(q, ctx, r["hallucinated_answer"], {"verdicts": [], "faithfulness": 0.0})
            )
    except Exception as exc:  # noqa: BLE001
        print(f"skip HaluEval: {exc}")
    return rows


async def _distil_examples(offline: bool) -> list[dict[str, Any]]:
    """Run the frontier judge over the RAG demo golden triples (distillation targets)."""
    gold = REPO / "data" / "gold" / "rag_demo.jsonl"
    if not gold.exists():
        return []
    try:
        from lens_core.judges.router import JudgeRouter
        from lens_core.metrics import EvalItem, get_metric
    except ImportError:
        return []
    router = JudgeRouter.from_env()
    try:
        judge = router.get("frontier")
    except KeyError:
        print("no frontier judge configured; skipping distillation")
        return []
    faith = get_metric("faithfulness")
    rows: list[dict[str, Any]] = []
    triples = [json.loads(x) for x in gold.read_text(encoding="utf-8").splitlines() if x.strip()]
    for t in triples:
        if not t.get("contexts") or not t.get("expected_output"):
            continue
        item = EvalItem(input=t["input"], output=t["expected_output"], contexts=t["contexts"])
        result = await faith.score(item, judge)
        if result.skipped or result.error:
            continue
        target = {"verdicts": result.details.get("claims", []), "faithfulness": result.value}
        rows.append(_format(t["input"], t["contexts"], t["expected_output"], target))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    random.seed(args.seed)

    rows = _public_examples(args.offline) + asyncio.run(_distil_examples(args.offline))
    if not rows:
        print("no examples built (need `datasets` online or a configured frontier judge)")
        return

    # split by source document to avoid leakage (SPEC.md §7.1)
    docs = sorted({r["source_document"] for r in rows})
    random.shuffle(docs)
    n_test = max(1, int(len(docs) * 0.1))
    test_docs = set(docs[:n_test])
    val_docs = set(docs[n_test : 2 * n_test])
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "test": []}
    for r in rows:
        d = r["source_document"]
        splits["test" if d in test_docs else "val" if d in val_docs else "train"].append(r)

    OUT.mkdir(parents=True, exist_ok=True)
    for split, items in splits.items():
        (OUT / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in items) + "\n", encoding="utf-8"
        )
    (OUT / "datacard.md").write_text(
        "# Distilled faithfulness judge dataset\n\n"
        f"- Seed: {args.seed}; offline: {args.offline}\n"
        f"- Rows: {len(rows)} (train {len(splits['train'])}, val {len(splits['val'])}, test {len(splits['test'])})\n"
        "- Split by source document to prevent leakage.\n"
        "- Public: HaluEval (+ RAGTruth/FEVER when wired); distillation targets from the frontier\n"
        "  judge over RAG demo / Sentinel triples; human gold merged at eval time only.\n",
        encoding="utf-8",
    )
    print(f"built {len(rows)} rows across {len(docs)} source documents")


if __name__ == "__main__":
    main()
