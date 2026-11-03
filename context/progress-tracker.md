# Progress Tracker

Update after every meaningful implementation change.

## Current phase

- Week 1 (plan: 4 weeks, ~5h/day).

## Current goal

- Week 1: environment, DB schema, Clerk, elder registration, pre-call hook, `session_token`, basic Dograh workflow.

## Completed

| ID | Summary | Verified |
|---|---|---|
| `INF-01` | Skeleton backend, ride-sim, frontend; compose PostgreSQL + pgvector | `/health` tests |
| `DB-01` | Core schema: users, elders, elder_family, call_sessions (`2799efe1c415`) | pytest on real PG |
| `AUTH-01` | Clerk JWT via JWKS, user sync webhook, `GET /api/me`, error shape | Live vs Clerk dev |
| `AUTH-02` | ClerkProvider vi-VN, `proxy.ts`, typed API client, role-gated `/admin` | Live vs Clerk dev |
| `UI-01` | Public pages `/`, `/demo`, sign-in/up (Touch the Light branding) | Headless Chrome 1440/390 |
| `REG-01a` | Elder registration + link requests with owner approval (`8c9a52a4bb0d`) | 77 tests |
| `REG-01b` | Dashboard: register form, elder list, approve/reject requests | E2E, 2 Clerk users |
| `ID-01` | Pre-call hook, `session_token`, `confirm-activation` tool | 107 tests |

## In progress

- None.

## Next

- `DG-01a`: Dograh service in `infra/docker-compose.yml`; verify the Dograh container reaches the backend (e.g. `host.docker.internal` `/health`).
- `DG-01b`: basic workflow in `dograh/`: pre-call hook mode `Always` → `/hooks/pre-call` (Bearer); greeting per `caller_status` with `{{preferred_name | bác}}`; consent prompt → HTTP tool `confirm_activation` (Preset Parameter `session_token = {{initial_context.session_token}}`); web call tests with `caller_number` for active, pending → `ACTIVE`, unknown.
- `CHK-01`: manual browser check of Clerk sign-in form styling (AUTH-02) and signed-in public header (UI-01).
- `OPS-01`: remove the orphaned admin user row (`user_3LE…`) from the dev DB; rename the Clerk application to "Touch the Light" (manual, Clerk Dashboard).

## Backlog (unscheduled)

- OSRM service in `infra/docker-compose.yml`, with the ride units.
- Web call simulation page; point `/demo` "Mở trang gọi thử" at it.
- Public "Tầm nhìn" / "Tài nguyên" pages (waiting for design).

## Open questions

- STT/TTS provider: Azure Speech vs Google Chirp (decide after vi-VN quality/latency test).
- Embedding dims: 768 vs 1536.
- Geocoding: self-hosted Nominatim/Photon vs Goong API.
- Real telephony provider (if time allows) and its caller ID format.
- In-call scam check trigger: per turn vs every N turns.
- Data retention period for transcripts and recordings.
- Public demo hotline number for `/demo` (depends on real telephony), and whether the footer should name the university.
- Orphaned elders: if an owner deletes their account, the elder stays but pending link requests have nobody to approve them.
- Link request notifications: owners only see requests on the dashboard until the Notification Service exists.

## Architecture decisions

- Clerk for web auth: fast integration, business data kept in PostgreSQL.
- Elder identity by phone + consent activation on first call: no account needed, records consent.
- Per-call `session_token` via Preset Parameter: LLM can't spoof identity.
- Self-built Ride Simulator, no Karhoo: no third-party dependency, full test control.
- Hybrid search in PostgreSQL: no extra infra, tolerant to STT errors.
- Telegram for urgent alerts, Email for reports: email too slow for scam alerts.
- Scam check split: real-time in-call + async post-call memory extraction.
- Registration of a taken number returns 202 `link_requested`: tells the requester the number is registered (no personal data); accepted as inherent to the spec.
- Keep Clerk `createRouteMatcher` in `proxy.ts` (deprecated, removed in Clerk's next major): clean 307s before rendering, and the backend guards data anyway. Revisit on the Clerk major upgrade.

## Session notes

- Tooling: npm 11+ required — npm 10 fails to resolve `@hookform/resolvers` optional peers (`ERESOLVE`). uv ≥0.13 `uv init --app` creates a `src/` package layout; services use a flat `app/` instead (no build-system).

- Tests: backend `pytest` needs `docker compose up` (infra); the suite drops/recreates `ai_companion_test` (`TEST_DATABASE_URL`, must end in `_test`) and runs migrations on it.

- Auth: Clerk dev instance configured (setup steps in README); webhook endpoint URL must include the `/webhooks/clerk` path. svix 2.x `Webhook.verify()` returns `None`; parse the body separately.

- Frontend: Next 16.4 + Clerk Core 3, both newer than most docs/training data. Read `frontend/node_modules/next/dist/docs/` and `@clerk/nextjs` types before using an API. Clerk dev instances answer cookie-less HTML requests with a handshake redirect (`dev-browser-missing`); curl checks need a cookie jar + `-L` first. In Git Bash, exported env values starting with `/` get rewritten to Windows paths (`/sign-in` → `C:/Program Files/Git/sign-in`); use `.env.local` or PowerShell (or `MSYS_NO_PATHCONV=1` for CLI args).

- Signed-in checks without a browser: Clerk Backend API (`CLERK_SECRET_KEY`) `sessions.createSession({userId})` → `sessions.getToken(id)` → request the frontend with `Authorization: Bearer <jwt>` (`clerkMiddleware` accepts header tokens); revoke the session after. Users created in Clerk get role `family` in the DB until the webhook delivers `user.updated`, so admin tests need the webhook (ngrok) or a manual DB role update. Dev-only: a non-admin opening `/admin` logs "Could not validate `instant`" (the layout redirect stops the child page from rendering); harmless.

- Browser E2E (used in REG-01b): run a prod frontend build against the real backend + Clerk dev. Sign test users in via Clerk sign-in tokens in headless Chrome. Sync their names/emails by delivering signed Clerk webhooks locally (`user.created`/`user.updated` signed with `CLERK_WEBHOOK_SECRET` the way `svix_headers` in `backend/tests/conftest.py` does, POSTed to `/webhooks/clerk`). Delete the test users and their data afterwards.

- Dograh: pre-call hook times out after 10s; web calls need hook mode `Always` + a `caller_number` context variable; greetings need a fallback for missing variables; check `{{initial_context.*}}` rendering in the tool test panel.
