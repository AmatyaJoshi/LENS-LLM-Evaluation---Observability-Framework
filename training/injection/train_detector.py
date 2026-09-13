"""Train the prompt-injection detector (SPEC.md §7.2).

DeBERTa-v3 (base or xsmall) sequence classifier, class-weighted cross-entropy, lr 2e-5,
3 epochs, max_len 512. Also supports a ModernBERT variant via --model. Logs to MLflow
(and W&B with --wandb), saves the model + tokenizer + metrics.json.

Requires training/requirements.txt in a GPU environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.common import set_seed, write_results

DATA = Path(__file__).parent / "data"
DEFAULT_OUT = Path(__file__).parent / "artifacts" / "detector"


def load_split(name: str) -> list[dict[str, object]]:
    path = DATA / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run build_dataset.py first")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="microsoft/deberta-v3-base")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--wandb", action="store_true")
    args = ap.parse_args()
    set_seed(args.seed)

    import evaluate
    import numpy as np
    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        Trainer,
        TrainingArguments,
    )

    train, val = load_split("train"), load_split("val")
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    def tok(batch: dict[str, list]) -> dict[str, list]:
        return tokenizer(batch["text"], truncation=True, max_length=args.max_len)

    ds_train = Dataset.from_list(train).map(tok, batched=True)
    ds_val = Dataset.from_list(val).map(tok, batched=True)

    # class weights for imbalance (SPEC.md §7.2: class-weighted CE)
    n_pos = sum(r["label"] for r in train)
    n_neg = len(train) - n_pos
    weights = torch.tensor(
        [len(train) / (2 * max(n_neg, 1)), len(train) / (2 * max(n_pos, 1))], dtype=torch.float
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        num_labels=2,
        id2label={0: "benign", 1: "injection"},
        label2id={"benign": 0, "injection": 1},
    )
    f1 = evaluate.load("f1")

    def metrics(eval_pred):  # type: ignore[no-untyped-def]
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {"f1": f1.compute(predictions=preds, references=labels)["f1"]}

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):  # type: ignore[no-untyped-def]
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            loss = torch.nn.functional.cross_entropy(
                outputs.logits, labels, weight=weights.to(outputs.logits.device)
            )
            return (loss, outputs) if return_outputs else loss

    training_args = TrainingArguments(
        output_dir=str(args.out / "checkpoints"),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        weight_decay=0.01,
        warmup_ratio=0.06,
        bf16=torch.cuda.is_available(),
        logging_steps=25,
        seed=args.seed,
        report_to=["wandb"] if args.wandb else ["mlflow"],
    )
    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=ds_train,
        eval_dataset=ds_val,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=metrics,
    )
    trainer.train()
    args.out.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    eval_metrics = trainer.evaluate()
    (args.out / "metrics.json").write_text(json.dumps(eval_metrics, indent=2), encoding="utf-8")
    (args.out / "model_card.json").write_text(
        json.dumps(
            {
                "base_model": args.model,
                "positive_index": 1,
                "version": "1",
                "max_len": args.max_len,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_results(
        "injection_train", {"model": args.model, "val_metrics": eval_metrics, "n_train": len(train)}
    )
    print(f"saved detector -> {args.out}")


if __name__ == "__main__":
    main()
