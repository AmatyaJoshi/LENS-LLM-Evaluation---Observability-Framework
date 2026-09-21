# TODO.md

Ordered by phase, then priority. `B#` refers to STATUS.md "Broken". Est. hours in brackets.

## Blocked on user

- [ ] Decide live-judge provider (Ollama local install recommended; else Groq/Gemini free). STATUS.md Q1
- [ ] Decide Docker on dev machine (enable WSL2/Hyper-V, or CI/VM-only). STATUS.md Q2
- [ ] Label ≥ 20 items with `lens label` once B1 lands. STATUS.md Q3
- [ ] Confirm Phase 1 provider: Oracle Cloud Always Free + Vercel Hobby (DECISIONS D5)

## Phase 0 follow-ups (before Phase 1 code)

- [ ] B1 link every `Score` to a trace or example; retry trajectory fetch; stable file `example_id` [3]
- [ ] B8 zero-cost guards: `BUDGET_*`, `cost_mode` in `/health`, UI badge, outbound allow-list, tests [4]
- [ ] Remove `OPENROUTER_API_KEY` from `.env` and from the router defaults; add `ollama/` and `groq/` defaults [1]
- [ ] Run 10 metrics × 5 gold items on the approved judge; confirm provenance fields; record cost line in COST.md [1]
- [ ] B2 read the failing compose CI logs and fix [2–4]
- [ ] B6 balanced offline injection corpus (benign + hard negatives) [2]
- [ ] B3 heuristic detector recall on the shipped corpus [2]
- [ ] B7 README: 124 tests, port notes, `.env.local` [0.5]
- [ ] B9 bump `next` past CVE-2025-66478 [0.5]
- [ ] Replace `/ci` 501 stub with the real route or delete it [0.5]

## Phase 1 — production deployment (days 3–8)

- [ ] Oracle Always Free ARM VM: Compose (clickhouse, postgres, redis, collector, api, worker), Caddy + DuckDNS TLS
- [ ] `apps/web` on Vercel Hobby pointing at the API
- [ ] `deploy/README.md` with exact steps and a cost table (all $0)
- [ ] Multi-tenancy: `org_id` on every ClickHouse table and Postgres model; scoped queries; API keys per org; signup → org → first key flow; migrations; row-level test (org A cannot read org B)
- [ ] Per-key ingest rate limits, Redis backpressure, `/health` + `/ready` per service, structured logs, status page route
- [ ] k6 ingest load test on the VM → `deploy/BENCH.md`

## Phase 2 — governance & compliance (days 6–10)

- [ ] PII redaction at ingest (regex + detector segments); per-org retention (`lens gc`); export + delete-my-org; admin audit log
- [ ] `SECURITY.md` with data-flow diagram and every third-party call
- [ ] Trust badge (red/amber/green from calibration) + judge model / prompt version / cost / κ on every score, prominent on trace detail
- [ ] Per-org consent flag before red-teaming URLs outside verified domains

## Phase 3 — monetization (days 8–12)

- [ ] Confirm pricing numbers with user before creating Stripe **test-mode** products
- [ ] Stripe Checkout + Customer Portal + webhooks (test keys only); ClickHouse usage metering; plan limits at ingest and in UI
- [ ] `docs/MONETIZATION.md`: rationale vs Langfuse/Arize/Braintrust/LangSmith, unit economics, CAC channels, 12-month model

## Phase 4 — UI/UX and pitch (days 12–16)

- [ ] Onboarding flow < 5 min with teaching empty states
- [ ] Landing page in `apps/web` (problem, 3 screenshots, pricing, "judge your judge", CTA)
- [ ] `docs/GALUXIUM.md`
- [ ] 3–4 min video recorded on the deployed instance (OBS)
