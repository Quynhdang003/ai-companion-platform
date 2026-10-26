# Progress Tracker

Update after every meaningful implementation change.

## Current phase

- Week 1 (plan: 4 weeks, ~5h/day).

## Current goal

- Week 1: environment, DB schema, Clerk, elder registration, pre-call hook, `session_token`, basic Dograh workflow.

## Completed

- `INF-01`: skeletons for `backend/` (FastAPI, uv, empty packages, pydantic-settings config, async Alembic init, no revisions), `ride-sim/` (FastAPI, uv), `frontend/` (Next.js 16 App Router, TS strict, Tailwind v4, shadcn/ui + sonner, Clerk/zod/RHF installed but not wired), `infra/docker-compose.yml` (PostgreSQL 17 + pgvector only), `dograh/` placeholder. Only `GET /health` on both Python services, one test each.

## In progress

- None.

## Next

- Add Dograh and OSRM services to `infra/docker-compose.yml` (deferred from `INF-01`; do with the tasks that need them).
- `DB-01`: schema `users`, `elders`, `elder_family`, `call_sessions`.
- `AUTH-01`: Clerk + JWT verification + user sync webhook.
- `REG-01`: elder registration form (E.164, duplicate → link request).
- `ID-01`: pre-call hook + `session_token` + `confirm_activation` tool.

## Open questions

- STT/TTS provider: Azure Speech vs Google Chirp (decide after vi-VN quality/latency test).
- Embedding dims: 768 vs 1536.
- Geocoding: self-hosted Nominatim/Photon vs Goong API.
- Real telephony provider (if time allows) and its caller ID format.
- In-call scam check trigger: per turn vs every N turns.
- Data retention period for transcripts and recordings.

## Architecture decisions

- Clerk for web auth: fast integration, business data kept in PostgreSQL.
- Elder identity by phone + consent activation on first call: no account needed, records consent.
- Per-call `session_token` via Preset Parameter: LLM can't spoof identity.
- Self-built Ride Simulator, no Karhoo: no third-party dependency, full test control.
- Hybrid search in PostgreSQL: no extra infra, tolerant to STT errors.
- Telegram for urgent alerts, Email for reports: email too slow for scam alerts.
- Scam check split: real-time in-call + async post-call memory extraction.

## Session notes

- Tooling: npm 11+ required — npm 10 fails to resolve `@hookform/resolvers` optional peers (`ERESOLVE`). uv ≥0.13 `uv init --app` creates a `src/` package layout; services use a flat `app/` instead (no build-system).

- Dograh notes: pre-call hook 10s timeout, web calls need hook mode `Always` + `caller_number` context variable; greeting needs fallback for missing variables; verify `{{initial_context.*}}` rendering in tool test panel.
