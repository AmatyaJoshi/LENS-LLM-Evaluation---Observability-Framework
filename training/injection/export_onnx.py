"""Export the trained injection detector to ONNX + int8 (SPEC.md §7.2).

Produces ``artifacts/onnx/{model.onnx, tokenizer.json, model_card.json}`` in the layout the
runtime ``OnnxDetector`` (lens_core.redteam.detector) loads via ``LENS_DETECTOR_PATH``. Target:
under 50 ms p95 on CPU. Dynamic int8 quantisation via optimum/onnxruntime.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

DEFAULT_MODEL = Path(__file__).parent / "artifacts" / "detector"
DEFAULT_OUT = Path(__file__).parent / "artifacts" / "onnx"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-quantize", action="store_true")
    args = ap.parse_args()

    from optimum.onnxruntime import ORTModelForSequenceClassification, ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    from transformers import AutoTokenizer

    args.out.mkdir(parents=True, exist_ok=True)
    print("exporting to ONNX…")
    model = ORTModelForSequenceClassification.from_pretrained(str(args.model), export=True)
    model.save_pretrained(str(args.out))
    tokenizer = AutoTokenizer.from_pretrained(str(args.model))
    tokenizer.save_pretrained(str(args.out))

    if not args.no_quantize:
        print("int8 dynamic quantisation…")
        quantizer = ORTQuantizer.from_pretrained(str(args.out))
        qconfig = AutoQuantizationConfig.avx512_vnni(is_static=False, per_channel=False)
        quantizer.quantize(save_dir=str(args.out), quantization_config=qconfig)
        # the runtime loads model.onnx; point it at the quantised file
        quantised = next(args.out.glob("*quantized*.onnx"), None)
        if quantised:
            shutil.copy(quantised, args.out / "model.onnx")

    # tokenizer.json is required by the runtime OnnxDetector
    if not (args.out / "tokenizer.json").exists():
        tokenizer.save_pretrained(str(args.out), legacy_format=False)

    card = {}
    card_path = args.model / "model_card.json"
    if card_path.exists():
        card = json.loads(card_path.read_text(encoding="utf-8"))
    card.setdefault("positive_index", 1)
    card.setdefault("version", "1")
    card["quantized"] = not args.no_quantize
    (args.out / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")

    print(f"exported -> {args.out}")
    print(f"serve it: export LENS_DETECTOR_PATH={args.out}")


if __name__ == "__main__":
    main()
