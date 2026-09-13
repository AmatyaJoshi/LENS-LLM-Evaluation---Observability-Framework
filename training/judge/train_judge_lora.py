"""Train the distilled faithfulness/hallucination judge (SPEC.md §7.1).

Qwen2.5-3B-Instruct (or Llama-3.2-3B) + LoRA (r=16, α=32) via TRL SFT on the
instruction→JSON format from build_distill_set.py. lr 1e-4, 2-3 epochs, max_len 4096,
bf16, cosine schedule, effective batch 32. Saves the adapter and merged weights for vLLM,
and registers a model card. Logs to MLflow (or W&B with --wandb).

Requires training/requirements.txt in a GPU environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.common import set_seed, write_results

DATA = Path(__file__).parent / "data"
DEFAULT_OUT = Path(__file__).parent / "artifacts" / "judge-lora"


def load_split(name: str) -> list[dict[str, object]]:
    path = DATA / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run build_distill_set.py first")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=8)  # effective batch 32
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--merge", action="store_true", help="also save merged fp16 weights for vLLM")
    ap.add_argument("--wandb", action="store_true")
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    set_seed(args.seed)

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def to_text(r: dict[str, object]) -> dict[str, str]:
        messages = [
            {"role": "system", "content": str(r["instruction"])},
            {"role": "user", "content": str(r["input"])},
            {"role": "assistant", "content": str(r["output"])},
        ]
        return {"text": tokenizer.apply_chat_template(messages, tokenize=False)}

    ds_train = Dataset.from_list(load_split("train")).map(to_text)
    ds_val = Dataset.from_list(load_split("val")).map(to_text)

    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map="auto"
    )
    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )
    sft_config = SFTConfig(
        output_dir=str(args.out / "checkpoints"),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        max_seq_length=args.max_len,
        bf16=True,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        seed=args.seed,
        report_to=["wandb"] if args.wandb else ["mlflow"],
        dataset_text_field="text",
    )
    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=ds_train,
        eval_dataset=ds_val,
        peft_config=peft_config,
        processing_class=tokenizer,
    )
    trainer.train()
    args.out.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))

    if args.merge:
        merged = trainer.model.merge_and_unload()
        merged.save_pretrained(str(args.out / "merged"))
        tokenizer.save_pretrained(str(args.out / "merged"))

    (args.out / "model_card.json").write_text(
        json.dumps(
            {
                "base_model": args.model,
                "adapter": "lora",
                "lora_r": args.lora_r,
                "lora_alpha": args.lora_alpha,
                "served_model_name": "lens-judge-small",
                "version": "1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_results(
        "judge_train", {"model": args.model, "n_train": len(ds_train), "eval": trainer.evaluate()}
    )
    print(f"saved judge adapter -> {args.out}")


if __name__ == "__main__":
    main()
