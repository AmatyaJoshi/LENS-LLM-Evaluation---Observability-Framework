# DECISIONS.md

Running log of non-obvious decisions. Newest first. Format: date · decision · why · alternatives.

## 2026-09-21 — Phase 0

- **D5 · Zero-cost policy overrides the hackathon brief's hosting suggestion.** The brief recommends
  Hetzner/Fly.io; COST.md forbids both. Phase 1 will target Oracle Cloud Always Free (ARM VM +
  Compose) with Vercel Hobby for the dashboard. *Pending user confirmation at the Phase 1 stop point.*
- **D4 · Runtime SQLite files removed from git.** `lens.db` and `lens_spans.db` were tracked and
  changed on every run; `mlflow.db` appeared at the repo root after training. All three are now
  ignored. Anyone needing seed data gets it from `lens ingest` of the fixtures, not from a binary blob.
- **D3 · `training/results/*.json` is no longer gitignored.** CLAUDE.md requires every cited number
  to point to a file in `training/results/`; that is impossible if the files are never committed.
  The two files from today's smoke run are committed but flagged non-citable in STATUS.md.
- **D2 · Phase 0 verified on the no-Docker path.** Docker Desktop's backend never started on the dev
  machine (no WSL). Rather than block, the whole loop was verified with the SQLite span store and the
  dev dashboard; compose verification is deferred to CI logs and the Phase 1 VM (STATUS.md B2).
- **D1 · Detector smoke run uses `prajjwal1/bert-tiny`, 1 epoch, CPU.** Goal was to prove the
  `build → train → eval → results/` convention end to end at $0, not to produce a model. The
  resulting numbers are degenerate and must not be cited.
