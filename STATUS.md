# STATUS — Phase 0 verification pass

Date: 2026-09-21 (Mon). Commit under test: `7124b86`. Machine: Windows 11 Pro, no WSL, Docker Desktop
backend never came up (see B2). Everything below was verified on the **no-Docker path**
(`LENS_SPAN_STORE=sqlite uv run lens serve` + `npm run dev`), which is what README calls
"No Docker (works without WSL)".

## Verdict

**Ready for live demo: NO.**

The end-to-end loop (ingest → trajectory → eval run → red team before/after defence → dashboard)
works locally with zero cost, and the checks are green. It is not demo-ready because:

1. **B1** every stored `Score` has `trace_id = NULL` and `example_id = NULL`, so per-trace scores,
   the labelling queue and "similar failures" are all unlinked;
2. no judge has been run against a **free, approved** provider (Ollama / Groq / Gemini free) — the
   only key on this machine is OpenRouter, which is not on the approved list;
3. `docker compose up --wait` fails in CI on the last three pushes and could not be run locally;
4. there are **0 human labels**, so the Judge Quality page has nothing to say about judges vs humans.

Estimated engineering to flip the verdict: **~16 h** (breakdown in "Broken").

## What was run and what happened

| Step | Result |
|---|---|
| `docker compose up -d --wait` | **Not run**: Docker Desktop backend never started in 30+ min (WSL not installed; backend log: "backend is not running"). CI's compose smoke job also fails (B2). |
| `uv run lens ingest tests/fixtures/otlp/openllmetry_python.json --endpoint http://localhost:8000` | OK. Trace `45bf200d…` appears in `/traces`; `/traces/{id}/trajectory` returns app `rag_demo`, 1 step, input "Which port is OTLP/HTTP on?", output "Port 4318." |
| Dashboard | Dev server on :3005 (port 3000 is taken by another app on this machine). `/`, `/traces`, `/traces/{id}`, `/trajectories`, `/judges`, `/redteam`, `/evaluations`, `/security`, `/labelling`, `/datasets` all return 200 with the API on :8000. |
| Demo step 1: `rag_demo` on :8100 | OK. Runs with the rule-based responder (no LLM key). Traces export to the API over OTLP/HTTP (404 traces stored after the run). |
| Demo step 2: `lens eval --dataset data/gold/rag_demo.jsonl --app rag_demo --target …/chat` | OK with `LENS_JUDGE_CASSETTE=tests/fixtures/judge_cassette.json`. 58 items × 5 metrics, 345 judge calls, $0. Run stored. Scores are uninformative (cassette returns canned answers → 1.0/1.0/1.0/1.0/0.0). |
| Demo step 3: `lens redteam … --defence none` | OK. 150 probes, **ASR 49.3 % (74/150)**, detector caught 4. Per category: indirect 100 %, jailbreak 69 %, direct 48.8 %, exfil 20 %, wallet 0 %, tool abuse 0 %. |
| Demo step 3b: `RAG_DEMO_DEFENCE=on … --defence input-sanitiser` | OK. **ASR 2.0 % (3/150)**, detector caught 0. Both runs visible on the Red Team page. |
| `uv run pytest -q` | **124 passed, 0 failed, 0 skipped** in 11 s (README says 114). |
| `ruff check`, `ruff format --check`, `mypy` | All clean (116 files formatted, 44 source files typed). |
| `cd apps/web && npm ci && npm run build` | OK, 14 routes. `npm test` (Vitest): 6 passed. npm warns next 15.5.3 has CVE-2025-66478 (B9). |
| Step 4: 10 metrics × 5 gold items on a **live** judge | **Not done.** No approved free provider available (Ollama not installed; OpenRouter is paid). Needs a decision — see "Questions". |
| Step 4: `Score` provenance | Confirmed on stored rows: `judge_model`, `judge_prompt_version` (e.g. `claim_extraction@1`), `cost_usd`, `latency_ms`, `version`, `rationale`. |
| Step 4: Judge Quality from real labels | **Not done.** `human_labels` table has 0 rows. `/judges/quality` renders between-judges κ/α/ρ with n = 1 (leftover from a 14 Sep OpenRouter run) and `vs_human: []`. `lens label` cannot be used until B1 is fixed (queue items carry no id). |
| Step 5: injection detector on CPU | Done as a **smoke run**: `build_dataset --offline` (1,071 rows) → `train_detector --model prajjwal1/bert-tiny --epochs 1 --max-len 128` (50 s CPU) → `eval_detector`. Two files written to `training/results/` (`20260921_7124b86_injection_{train,eval}.json`). **Numbers are not citable**: the offline set is 98.6 % positive and the model predicts "injection" for every input (TN 0, FPR 1.0, hard-negative FPR 1.0). |
| Step 6: grep audit | No `TODO`, `FIXME`, `NotImplemented`, `xfail`, `skip`, `mock` in Python/TS source. "placeholder" hits are all HTML input placeholders. One stub router: `/ci` returns 501 ("scheduled for phase 8"). |

### Test classification

| Bucket | Count |
|---|---|
| Total collected | 124 |
| Passed / failed / skipped | 124 / 0 / 0 |
| Skip / xfail markers in source | 0 |
| Test files that replay the judge cassette (`tests/fixtures/judge_cassette.json`) | 6 (`test_metrics`, `test_judges`, `test_redteam`, `test_evals_api`, `test_cli_eval`, `test_assistant_api`) |
| Tests that call a live LLM | 0 |

## What is mocked or degraded

- **Judge**: cassette only. `JudgeRouter.from_env` supports LiteLLM models, so Ollama
  (`ollama/llama3.1:8b`) or Groq will work by setting `LENS_JUDGE_FRONTIER_MODEL`, but this has not
  been exercised.
- **Demo app answers** are rule-based unless `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` is set. No
  Ollama option yet.
- **Metrics coverage**: 10 metrics are registered; `DEFAULT_METRICS` runs 5. `tool_correctness`,
  `trajectory_efficiency`, `task_completion`, `safety`, `calibration` were exercised only by unit
  tests today.
- **`/ci` API route** is a 501 stub. `lens ci` works client-side (`lens eval` + `--baseline-file`)
  and CI dogfoods it successfully; the stub is misleading, not blocking.
- **Zero-cost guards**: none exist yet (no `BUDGET_*`, no `cost_mode` in `/health`, no outbound
  allow-list). Required by COST.md (B8).

## Broken

| # | Problem | Evidence | Fix | Est. |
|---|---|---|---|---|
| B1 | `Score` rows never link to a trace or example | 314/314 rows in `lens.db` have both ids NULL. File datasets carry no UUID `example_id`; the runner GETs `/traces/{id}/trajectory` right after the target answers while the demo's OTLP export is async → 404 → swallowed → `trace_id=None`. | Store the target-returned `trace_id` even when the trajectory fetch fails; retry the fetch with backoff; derive a stable `example_id` for file datasets. Test: eval run → every score has a trace or example id. | 3 h |
| B2 | Compose stack unverified | CI job `docker compose up --wait` failed on `7124b86`, `9beb0e8`, `febf4e6`; local Docker backend never started (no WSL/Hyper-V confirmed). | Read the CI logs (needs `gh` or a token), fix the failing service, and/or verify on the Phase 1 VM. | 2–4 h |
| B3 | Heuristic injection detector barely recognises the shipped corpus | `eval_detector` heuristic: recall 0.0097 (1/103) on the test split; red team "detector caught 4/74". | Decide whether the regex set is too narrow or the dataset is mostly mutated variants; widen patterns or fix labels. | 2 h |
| B4 | `training/results/*.json` was gitignored | Contradicts CLAUDE.md ("no number unless it points to a file in training/results"). | **Fixed in this commit** (un-ignored). | done |
| B5 | Runtime SQLite state committed | `lens.db`, `lens_spans.db` tracked and modified by every run; `mlflow.db` created at repo root. | **Fixed in this commit** (removed from index, ignored). | done |
| B6 | `build_dataset --offline` yields a degenerate dataset | 1,044 positive / 15 negative; trained classifier flags everything. | Bundle a benign + hard-negative corpus (READMEs, code comments, instructions-about-instructions) so offline builds are balanced. | 2 h |
| B7 | README drift | "114 tests" (actual 124); quick start assumes :3000/:8000 free. | Update README; document `.env.local` port override. | 0.5 h |
| B8 | No cost/budget guards | See COST.md. | `BUDGET_*` env, `cost_mode` in `/health` + UI badge, outbound allow-list at startup, tests that trip the caps. | 4 h |
| B9 | `next@15.5.3` CVE-2025-66478 | npm warning during `npm ci`. | Bump to patched 15.5.x, rebuild. | 0.5 h |

## Questions (stopping here per the rules)

1. **Live judge provider** for step 4 and all later phases. Recommended: **install Ollama locally**
   (`llama3.1:8b`, ~5 GB download, free, on the approved list). Alternatives: Groq free tier or
   Gemini free tier (no card). The `OPENROUTER_API_KEY` in `.env` is a paid provider and is not on
   the approved list; I propose deleting it from `.env` and from `LLM_KEY_ENV` defaults.
2. **Docker on this machine**: enabling WSL2 or Hyper-V needs admin. Alternatively accept that compose
   is verified only in CI and on the Phase 1 VM.
3. **Human labels**: ≥ 20 labels must come from a person. After B1 is fixed I will prepare a
   20-item disagreement queue for you to label with `lens label`.

## Cost check

Services touched: GitHub REST API (unauthenticated), Hugging Face Hub (one 17 MB model download),
PyPI/npm, local CPU. LLM calls: 0. Credits used: $0. Risk before deadline: none from today's work.
