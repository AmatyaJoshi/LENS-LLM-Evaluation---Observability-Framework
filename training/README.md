# Lens training pipelines

Two models (SPEC.md §7), each following the same convention: `build_*` (deterministic, seeded,
writes JSONL + datacard) → `train_*` (HF/TRL, MLflow/W&B, saves weights + `metrics.json`) →
`eval_*` (writes `results/<date>_<sha>_*.json` + plots) → `export_*`.

```bash
pip install -r training/requirements.txt      # GPU env

# Prompt-injection detector (phase 6)
python -m training.injection.build_dataset            # or --offline
python -m training.injection.train_detector --model microsoft/deberta-v3-base
python -m training.injection.eval_detector
python -m training.injection.export_onnx --model training/injection/artifacts/detector
export LENS_DETECTOR_PATH=training/injection/artifacts/onnx   # live detection in the API

# Distilled faithfulness/hallucination judge (phase 7)
export ANTHROPIC_API_KEY=...                           # for distillation targets
python -m training.judge.build_distill_set
python -m training.judge.train_judge_lora --merge
python -m training.judge.train_deberta_nli            # cheaper NLI baseline
python -m training.judge.eval_judge --tiers frontier,local --plot
```

Every number cited in the top-level README points to a file in `training/results/`
(CLAUDE.md). Nothing is claimed until you run the pipeline. Model cards are in
`training/MODEL_CARDS/`.
