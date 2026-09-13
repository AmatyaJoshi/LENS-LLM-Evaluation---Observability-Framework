"""Prompt-injection detector (SPEC.md §6.5, §7.2).

Two implementations behind one interface:

* ``OnnxDetector``: the fine-tuned DeBERTa classifier exported to ONNX int8 by
  ``training/injection/export_onnx.py``. Sliding window over 512 tokens, score =
  max window probability. Loaded when ``LENS_DETECTOR_PATH`` points at a
  directory containing ``model.onnx`` and ``tokenizer.json``.
* ``HeuristicDetector``: weighted regex rules for the well-known injection,
  jailbreak and exfiltration tactics. Fast, dependency-free, and the fallback
  when no trained model is present. Its version string makes the provenance
  explicit wherever a score is stored (``lens.security.detector``).

Both return a ``DetectionResult`` with a score in [0, 1] and human-readable reasons.
"""

from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

DEFAULT_THRESHOLD = 0.5


class DetectionResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    flagged: bool
    reasons: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0


class InjectionDetector(Protocol):
    name: str
    version: str
    threshold: float

    def score(self, text: str) -> DetectionResult: ...
    def score_batch(self, texts: Sequence[str]) -> list[DetectionResult]: ...


# ---------------------------------------------------------------------------------------------
# Heuristic detector
# ---------------------------------------------------------------------------------------------

# (rule id, weight, compiled pattern). Weights combine as 1 − Π(1 − w).
_RULES: list[tuple[str, float, re.Pattern[str]]] = [
    (
        "instruction_override",
        0.85,
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your)\b[^.\n]{0,30}\b(instruction|prompt|rule|guideline|directive)s?\b",
            re.I,
        ),
    ),
    (
        "new_persona",
        0.6,
        re.compile(
            r"\byou are now\b|\bfrom now on,? you (are|will|must)\b|\bact as (an? )?(unrestricted|unfiltered|jailbroken)\b|\bpretend (to be|you are)\b[^.\n]{0,40}\b(no|without) (rules|restrictions|filters)\b",
            re.I,
        ),
    ),
    (
        "dan_style",
        0.7,
        re.compile(r"\b(DAN|do anything now|developer mode|god mode|jailbreak)\b", re.I),
    ),
    (
        "prompt_extraction",
        0.75,
        re.compile(
            r"\b(reveal|print|show|repeat|output|display|leak|dump)\b[^.\n]{0,40}\b(system prompt|hidden prompt|initial prompt|your instructions|the instructions above|everything above|your rules|configuration)\b",
            re.I,
        ),
    ),
    (
        "secret_request",
        0.6,
        re.compile(
            r"\b(api[_ -]?key|password|secret|token|credential)s?\b[^.\n]{0,40}\b(reveal|show|print|tell|give|send)\b|\b(reveal|show|print|tell|give|send)\b[^.\n]{0,40}\b(api[_ -]?key|password|secret|token|credential)s?\b",
            re.I,
        ),
    ),
    ("exfil_markdown_image", 0.9, re.compile(r"!\[[^\]]*\]\(https?://[^)\s]*[?&][^)\s]*\)", re.I)),
    (
        "exfil_url_with_data",
        0.7,
        re.compile(r"https?://[^\s)]+[?&](data|q|payload|secret|content|ctx|k)=", re.I),
    ),
    (
        "hidden_instruction",
        0.7,
        re.compile(
            r"\b(do not|don't|never) (tell|inform|mention|reveal)\b[^.\n]{0,30}\b(user|human|operator)\b|\bthis is a (secret|hidden) (instruction|message)\b",
            re.I,
        ),
    ),
    (
        "role_markers",
        0.6,
        re.compile(
            r"<\|im_start\|>|<\|system\|>|\[INST\]|<<SYS>>|###\s*(system|instruction)\b|BEGIN (SYSTEM|ADMIN) (PROMPT|MESSAGE)",
            re.I,
        ),
    ),
    (
        "tool_coercion",
        0.7,
        re.compile(
            r"\b(call|invoke|run|execute|use)\b[^.\n]{0,30}\b(tool|function|command)\b[^.\n]{0,40}\b(delete|drop|remove|rm -rf|transfer|pay|send (money|funds|email))\b",
            re.I,
        ),
    ),
    (
        "mark_clean",
        0.8,
        re.compile(
            r"\b(mark|report|flag|classify)\b[^.\n]{0,30}\b(this|the) (file|code|document|input)\b[^.\n]{0,30}\b(as )?(clean|safe|approved|passing)\b",
            re.I,
        ),
    ),
    ("encoding_blob", 0.35, re.compile(r"(?:[A-Za-z0-9+/]{4}){20,}={0,2}")),
    ("zero_width", 0.5, re.compile(r"[​‌‍⁠﻿]{3,}")),
    (
        "translate_above",
        0.5,
        re.compile(
            r"\b(translate|summari[sz]e|repeat|copy)\b[^.\n]{0,20}\b(everything|all( the)? text|the text|the content) (above|before this)\b",
            re.I,
        ),
    ),
    (
        "payload_split",
        0.4,
        re.compile(
            r"\b(combine|concatenate|join)\b[^.\n]{0,30}\b(part|piece|fragment)s?\b[^.\n]{0,40}\b(then|and) (execute|follow|run|obey)\b",
            re.I,
        ),
    ),
]

# Text that looks like documentation about injections should score lower (hard negatives).
_DOC_CONTEXT = re.compile(
    r"\b(for example|e\.g\.|such as|is an attack where|detector|classifier|this pattern|the phrase)\b",
    re.I,
)
_CODE_FENCE = re.compile(r"```")


class HeuristicDetector:
    name = "heuristic"
    version = "1.0"

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    def score(self, text: str) -> DetectionResult:
        t0 = time.perf_counter()
        if not text:
            return DetectionResult(score=0.0, flagged=False)
        reasons: list[str] = []
        survive = 1.0
        for rule_id, weight, pattern in _RULES:
            hits = pattern.findall(text)
            if hits:
                n = len(hits)
                w = 1 - (1 - weight) ** min(n, 3)  # repeated hits increase confidence, capped
                survive *= 1 - w
                reasons.append(f"{rule_id}×{n}" if n > 1 else rule_id)
        score = 1 - survive
        # Dampen when the text reads like documentation or code discussing the pattern.
        if reasons and (_DOC_CONTEXT.search(text) or _CODE_FENCE.search(text)):
            score *= 0.6
            reasons.append("dampened:documentation_context")
        score = round(min(1.0, max(0.0, score)), 4)
        return DetectionResult(
            score=score,
            flagged=score >= self.threshold,
            reasons=reasons,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    def score_batch(self, texts: Sequence[str]) -> list[DetectionResult]:
        return [self.score(t) for t in texts]


# ---------------------------------------------------------------------------------------------
# ONNX detector (trained model)
# ---------------------------------------------------------------------------------------------


class OnnxDetector:
    name = "deberta-onnx"

    def __init__(
        self,
        model_dir: Path,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        max_len: int = 512,
        stride: int = 384,
    ) -> None:
        import json

        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.threshold = threshold
        self.max_len = max_len
        self.stride = stride
        self._tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(os.environ.get("LENS_DETECTOR_THREADS", "2"))
        self._sess = ort.InferenceSession(
            str(model_dir / "model.onnx"), opts, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self._sess.get_inputs()}
        card = model_dir / "model_card.json"
        meta = json.loads(card.read_text(encoding="utf-8")) if card.exists() else {}
        self.version = str(meta.get("version", "unknown"))
        self.positive_index = int(meta.get("positive_index", 1))

    def _windows(self, ids: list[int]) -> list[list[int]]:
        if len(ids) <= self.max_len:
            return [ids]
        out: list[list[int]] = []
        for start in range(0, len(ids), self.stride):
            out.append(ids[start : start + self.max_len])
            if start + self.max_len >= len(ids):
                break
        return out

    def score(self, text: str) -> DetectionResult:
        return self.score_batch([text])[0]

    def score_batch(self, texts: Sequence[str]) -> list[DetectionResult]:
        import numpy as np

        t0 = time.perf_counter()
        results: list[DetectionResult] = []
        for text in texts:
            enc = self._tok.encode(text or "")
            best = 0.0
            for window in self._windows(enc.ids):
                feed = {"input_ids": np.array([window], dtype=np.int64)}
                if "attention_mask" in self._inputs:
                    feed["attention_mask"] = np.ones((1, len(window)), dtype=np.int64)
                if "token_type_ids" in self._inputs:
                    feed["token_type_ids"] = np.zeros((1, len(window)), dtype=np.int64)
                logits = self._sess.run(None, feed)[0][0]
                z = [float(v) for v in logits]
                m = max(z)
                probs = [math.exp(v - m) for v in z]
                p = probs[self.positive_index] / sum(probs)
                best = max(best, p)
            results.append(
                DetectionResult(
                    score=round(best, 4),
                    flagged=best >= self.threshold,
                    reasons=[f"{self.name}@{self.version}"],
                    latency_ms=(time.perf_counter() - t0) * 1000 / len(texts),
                )
            )
        return results


@lru_cache(maxsize=1)
def get_detector() -> InjectionDetector:
    """Trained ONNX detector when ``LENS_DETECTOR_PATH`` is set and loadable, else heuristics."""
    path = os.environ.get("LENS_DETECTOR_PATH")
    threshold = float(os.environ.get("LENS_DETECTOR_THRESHOLD", str(DEFAULT_THRESHOLD)))
    if path:
        try:
            return OnnxDetector(Path(path), threshold=threshold)
        except Exception:  # noqa: BLE001 - fall back loudly via version string
            pass
    return HeuristicDetector(threshold=threshold)
