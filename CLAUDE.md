# Lens — conventions for Claude Code
- Read SPEC.md first. §4 semantic-convention mapping and §3 data model are contracts; changes require a SPEC.md edit in the same PR.
- Python 3.12 + uv + ruff (100 cols) + mypy --strict on packages/lens-core. TS strict mode, eslint, prettier in apps/web and packages/lens-sdk-ts.
- Metrics are pure and unit-tested with recorded judge cassettes; never call a live LLM in tests.
- Every judge prompt is a versioned .md under judges/prompts; bump version on any edit; Score rows record the version.
- ClickHouse migrations in apps/api/migrations/clickhouse, Postgres via Alembic. Never hand-edit prod schema.
- No metric number appears in README unless it points to a file in training/results or bench results.
- Probes must never contain real-world harmful instructions; success criteria are policy violations of the target only.
- One phase = one PR; conventional commits; ask before adding dependencies.
