# Contributing to Lens

Thanks for your interest. Lens is a spec-driven monorepo — read `SPEC.md` and
`CLAUDE.md` first; §3 (data model) and §4 (semantic-convention mapping) are
contracts, and any change to them must edit `SPEC.md` in the same PR.

## Setup

```bash
uv sync                       # Python 3.12 workspace
cd apps/web && npm ci         # dashboard
```

Copy `.env.example` to `.env`. Without Docker use `LENS_SPAN_STORE=sqlite` and
`LENS_POSTGRES_DSN=sqlite:///./lens.db`.

## Checks (run before opening a PR)

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
cd apps/web && npm run lint && npm run typecheck && npm run build
```

- Python: ruff (100 cols) + mypy --strict on `packages/lens-core`.
- Metrics are pure and unit-tested with recorded judge cassettes — **never call a
  live LLM in tests.**
- Every judge prompt is a versioned `.md`; bump the version on any edit.
- No metric number goes in the README unless it points to a file under
  `training/results/`.
- Probes must never contain real-world harmful instructions; success is a policy
  violation of the target only.

## Conventions

One phase = one PR; conventional commits; ask before adding dependencies.
See `SPEC.md §10` for the phase plan.
