"""DeBERTa NLI baseline judge (SPEC.md §7.1).

Fine-tune ``deberta-v3-large`` as a 3-way NLI classifier on (claim, context) pairs
{entailment→supported, contradiction→contradicted, neutral→unverifiable}. The SPEC notes
this cheaper baseline will likely win on cost; eval_judge.py reports that honestly. Pairs are
derived from the distill set's per-claim verdicts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.common import set_seed, write_results

DATA = Path(__file__).parent / "data"
DEFAULT_OUT = Path(__file__).parent / "artifacts" / "judge-deberta"
LABELS = {"supported": 0, "contradicted": 1, "unverifiable": 2}


def pairs_from_split(name: str) -> list[dict[str, object]]:
    path = DATA / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run build_distill_set.py first")
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        context = "\n".join(r.get("contexts", []))
        target = json.loads(r["output"]) if isinstance(r["output"], str) else r["output"]
        for v in target.get("verdicts", []):
            claim = v.get("claim")
            verdict = v.get("verdict")
            if claim and verdict in LABELS:
                rows.append({"premise": context, "hypothesis": claim, "label": LABELS[verdict]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="microsoft/deberta-v3-large")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    set_seed(args.seed)

    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        Trainer,
        TrainingArguments,
    )

    train, val = pairs_from_split("train"), pairs_from_split("val")
    if not train:
        raise SystemExit("no (claim, context) pairs; the distill set has no per-claim verdicts")
    tok = AutoTokenizer.from_pretrained(args.model)

    def encode(b: dict[str, list]) -> dict[str, list]:
        return tok(b["premise"], b["hypothesis"], truncation=True, max_length=args.max_len)

    ds_train = Dataset.from_list(train).map(encode, batched=True)
    ds_val = Dataset.from_list(val).map(encode, batched=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=3, id2label={v: k for k, v in LABELS.items()}, label2id=LABELS
    )
    targs = TrainingArguments(
        output_dir=str(args.out / "checkpoints"),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        eval_strategy="epoch",
        save_strategy="epoch",
        bf16=torch.cuda.is_available(),
        logging_steps=25,
        seed=args.seed,
        report_to=["mlflow"],
    )
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=ds_train,
        eval_dataset=ds_val,
        data_collator=DataCollatorWithPadding(tok),
    )
    trainer.train()
    args.out.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(args.out))
    tok.save_pretrained(str(args.out))
    (args.out / "model_card.json").write_text(
        json.dumps(
            {"base_model": args.model, "task": "nli-3way", "labels": LABELS, "version": "1"},
            indent=2,
        ),
        encoding="utf-8",
    )
    write_results("judge_deberta_train", {"n_pairs": len(train), "eval": trainer.evaluate()})
    print(f"saved DeBERTa NLI judge -> {args.out}")


if __name__ == "__main__":
    main()
