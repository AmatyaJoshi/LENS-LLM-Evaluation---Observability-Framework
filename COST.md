# COST.md — zero-cost policy for Lens

This project must cost the team **$0**. Before adding any external service, hosted dependency,
cloud resource, model API, domain or analytics tool: confirm it is free for our usage and add a row
below. If a requirement can only be met with money, stop and ask; propose the free alternative
first. Never add a payment card to any account. Never create resources outside a free tier.

## Approved stack

| Layer | Choice | Not allowed |
|---|---|---|
| LLM inference | Ollama on the Docker host (`qwen2.5-coder:7b` code, `llama3.1:8b` text, `mistral` fallback). Cloud fallback only Google Gemini free tier or Groq free tier (no card). | OpenRouter, Anthropic/OpenAI paid keys |
| Compute / hosting | Oracle Cloud Always Free ARM VM (primary) with Docker Compose; Render free tier (backup, sleeps); frontend on Vercel Hobby or Cloudflare Pages | Fly.io, Railway, Hetzner, DigitalOcean |
| Data | Postgres / Redis / ClickHouse in Compose on the free VM; or Neon / Supabase free Postgres and Upstash free Redis, with retention/GC jobs keeping sizes under the limits | managed paid tiers |
| Domains / TLS | platform subdomains or DuckDNS + Caddy (Let's Encrypt) | purchased domains |
| Analytics | self-hosted Umami on the VM, or PostHog free tier | Plausible |
| Payments | Stripe **test mode** only | live mode |
| CI | GitHub Actions on the public repo, jobs < 10 min | private-repo minutes |
| Tooling | OBS (video), k6 (load), draw.io / Mermaid (diagrams) | |

## Services in use (keep current)

| Service | Free-tier limit | In-code guard | When the limit is hit |
|---|---|---|---|
| GitHub (repo, Actions, REST API) | Public repo: unlimited Actions minutes; REST 60 req/h unauthenticated | CI jobs kept < 10 min | Jobs queue; nothing paid |
| Hugging Face Hub (model/dataset downloads) | Free, rate-limited | `HF_HUB_DISABLE_TELEMETRY=1`; downloads cached | Retry later; nothing paid |
| PyPI / npm | Free | — | — |
| Ollama (planned, local/VM) | Free, bounded by VM CPU/RAM | `BUDGET_LLM_CALLS_PER_RUN`, `BUDGET_LLM_TOKENS_PER_DAY` (B8, pending) | `cost_mode=degraded`: deterministic/template path, UI badge |
| Groq / Gemini free tier (planned fallback) | Groq: per-minute + per-day request caps; Gemini: per-day request caps (see provider pages, no card) | same budget guards; provider host must be on the allow-list | Fall back to Ollama, then degraded |
| Oracle Cloud Always Free (planned) | 4 OCPU / 24 GB ARM, 200 GB block storage, 10 TB egress/mo | ClickHouse TTL + `lens gc` retention keep disk < 150 GB | Retention job deletes oldest spans; alert in status page |
| Vercel Hobby (planned) | 100 GB bandwidth/mo, non-commercial | static export where possible | Move frontend to Cloudflare Pages |
| Stripe test mode (planned) | Free | test keys only, checked in CI (`sk_test_` prefix) | n/a |

## Required in-code guards (tracked as B8 in STATUS.md / TODO.md)

- `BUDGET_*` env vars for LLM calls, external API calls and storage, defaulting to free-tier-safe
  values.
- `/health` reports `cost_mode: normal | degraded`; the dashboard shows a badge when degraded.
- Startup log lists every outbound host; anything not on the allow-list fails closed.
- Tests assert the guards trip: call cap reached → degraded path, never an exception or a paid retry.

## Cost log

| Date | Step | Services touched | LLM calls | Credits used | Risk |
|---|---|---|---|---|---|
| 2026-09-21 | Phase 0 verification | GitHub REST (unauth), HF Hub (17 MB model), PyPI, npm, local CPU | 0 | $0 | none |
