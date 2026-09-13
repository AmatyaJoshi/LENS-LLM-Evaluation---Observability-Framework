"""Build the prompt-injection detector dataset (SPEC.md §7.2).

Sources (positives): public injection/jailbreak sets (``deepset/prompt-injections``,
``jackhhao/jailbreak-classification``, ``allenai/wildjailbreak`` safe subset) plus the
Lens probe corpus and its deterministic mutators (data/probes).
Sources (negatives): benign instruction/chat data (Alpaca, UltraChat samples) and — CRITICAL
per SPEC — *hard negatives*: benign texts that discuss instructions or contain code/comments,
so the model does not flag every README.

Deterministic and seeded. Writes train/val/test JSONL plus a datacard. Public datasets are
optional: with ``--offline`` (or when ``datasets`` is unavailable) the builder uses only the
Lens probe corpus and a bundled hard-negative set, so the pipeline runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "data"
PROBES = REPO / "data" / "probes"

# Bundled hard negatives: benign text that *talks about* instructions or contains code/comments.
HARD_NEGATIVES = [
    "The README explains how to configure the app: edit config.yaml and set the port.",
    "# This function ignores case when comparing strings.",
    "To reset your password, follow the instructions in the account settings page.",
    "Our style guide says: do not use the word 'very'; prefer a stronger adjective.",
    "The tutorial walks through overriding the default theme in your settings file.",
    "def parse(cmd):  # ignore comments starting with '#'\n    return cmd.split()",
    "The policy document describes the steps an administrator must follow to grant access.",
    "In this lesson we learn how prompt injection works so we can defend against it.",
    "The error says 'permission denied'; run the command with the correct role.",
    "Please review the pull request and leave comments on any lines that need changes.",
    "System design note: the scheduler should retry failed jobs with backoff.",
    "The recipe instructs you to ignore the first set of measurements and use the metric ones.",
    "Chapter 3 covers how assistants follow system prompts and why alignment matters.",
    "// TODO: refactor this once the new API ships",
    "The onboarding guide tells new hires to reset their password on day one.",
]

BENIGN_CHAT = [
    "What's the weather like in Paris today?",
    "Can you summarise this article about renewable energy?",
    "Translate 'good morning' into Spanish.",
    "Write a haiku about the ocean.",
    "What are the ingredients for a classic margherita pizza?",
    "Explain how photosynthesis works in simple terms.",
    "Help me draft a polite email declining a meeting.",
    "What's the difference between TCP and UDP?",
    "Recommend three books on behavioural economics.",
    "How do I sort a list of dictionaries by a key in Python?",
    "What time zone is New York in?",
    "Give me a quick recipe for banana bread.",
]


def _probe_positives() -> list[str]:
    try:
        from lens_core.redteam import apply_deterministic, load_probes
        from lens_core.redteam.mutators import DETERMINISTIC
    except ImportError:
        return []
    if not PROBES.exists():
        return []
    probes = load_probes(PROBES)
    texts: list[str] = []
    for p in probes:
        payload = p.payload or " ".join(m.content for m in p.messages)
        if payload:
            texts.append(payload)
        for variant in apply_deterministic(p, list(DETERMINISTIC)):
            if variant.payload:
                texts.append(variant.payload)
    return texts


def _public_positives_negatives(offline: bool) -> tuple[list[str], list[str]]:
    if offline:
        return [], []
    try:
        from datasets import load_dataset
    except ImportError:
        print("datasets not installed; building offline from the Lens corpus only")
        return [], []
    pos: list[str] = []
    neg: list[str] = []
    try:
        ds = load_dataset("deepset/prompt-injections", split="train")
        for row in ds:
            (pos if row["label"] == 1 else neg).append(row["text"])
    except Exception as exc:  # noqa: BLE001
        print(f"skip deepset/prompt-injections: {exc}")
    try:
        ds = load_dataset("jackhhao/jailbreak-classification", split="train")
        for row in ds:
            label = str(row.get("type", row.get("label", ""))).lower()
            (pos if "jail" in label or label == "1" else neg).append(row["prompt"])
    except Exception as exc:  # noqa: BLE001
        print(f"skip jackhhao/jailbreak-classification: {exc}")
    return pos, neg


def _rows(texts: list[str], label: int, source: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for t in texts:
        key = t.strip()
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        out.append({"text": key, "label": label, "source": source})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use only the bundled + Lens corpus")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--test-frac", type=float, default=0.1)
    args = ap.parse_args()
    random.seed(args.seed)

    pub_pos, pub_neg = _public_positives_negatives(args.offline)
    rows: list[dict[str, Any]] = []
    rows += _rows(_probe_positives(), 1, "lens_probes")
    rows += _rows(pub_pos, 1, "public_injection")
    rows += _rows(HARD_NEGATIVES, 0, "hard_negative")
    rows += _rows(BENIGN_CHAT, 0, "benign_chat")
    rows += _rows(pub_neg, 0, "public_benign")

    random.shuffle(rows)
    n = len(rows)
    n_test = int(n * args.test_frac)
    n_val = int(n * args.val_frac)
    splits = {
        "test": rows[:n_test],
        "val": rows[n_test : n_test + n_val],
        "train": rows[n_test + n_val :],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    counts: dict[str, dict[str, int]] = {}
    for split, items in splits.items():
        (OUT / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in items) + "\n", encoding="utf-8"
        )
        counts[split] = {
            "total": len(items),
            "positive": sum(1 for r in items if r["label"] == 1),
            "hard_negative": sum(1 for r in items if r["source"] == "hard_negative"),
        }

    (OUT / "datacard.md").write_text(
        "# Prompt-injection detector dataset\n\n"
        f"- Seed: {args.seed}; offline: {args.offline}\n"
        f"- Splits: {json.dumps(counts, indent=2)}\n"
        "- Positives: Lens probe corpus + deterministic mutators, plus public injection/jailbreak\n"
        "  sets when online.\n"
        "- Negatives: benign chat + **hard negatives** (text discussing instructions, code/comments)\n"
        "  so the detector does not flag every README (SPEC.md §7.2).\n"
        "- Held-out mutator families for the robustness eval are produced by eval_detector.py, not here.\n",
        encoding="utf-8",
    )
    print(f"built {n} rows: {counts}")


if __name__ == "__main__":
    main()
