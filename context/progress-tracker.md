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
| `DG-01a` | Self-hosted Dograh 1.50.0 in compose, own Postgres/Redis/MinIO, backend reachable from it | Healthchecks; container → host `/health` 200 |
| `DG-01b` | Dograh identity + consent workflow, `confirm_activation` tool, exports in `dograh/` | Text chat (Gemini): active, pending → ACTIVE, unknown |
| `UI-02` | Public copy: family sees call time/duration only, no call summaries | Lint + build; `/`, `/demo` at 1440/390 |
| `CALL-01a` | End-of-call webhook `/hooks/call-ended` → `call_logs` (`87d572f79894`); transcript for consented callers only | 134 tests; real Dograh transcript format |

## In progress

- None.

## Next

- `CALL-01b`: Webhook node on the DG-01b workflow → `http://host.docker.internal:8000/hooks/call-ended` (payload template in the CALL-01 plan), re-export `dograh/`, E2E by text chat: ACTIVE → transcript stored, unknown → metadata only.
- `DG-01c`: Azure Speech vi-VN STT/TTS (voice `vi-VN-HoaiMyNeural`) on the DG-01b workflow; run the voice web-call checklist in `dograh/README.md` (ACTIVE greeting within ~2s, consent by voice, unknown, backend down). The consent prompt should say family can't read the conversation.
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
- Family sees call metadata + scam alerts only, never transcripts or memories; no per-call summaries: elder privacy; content stays for memory and scam analysis.
- Keep Clerk `createRouteMatcher` in `proxy.ts` (deprecated, removed in Clerk's next major): clean 307s before rendering, and the backend guards data anyway. Revisit on the Clerk major upgrade.

## Session notes

- Tooling: npm 11+ required — npm 10 fails to resolve `@hookform/resolvers` optional peers (`ERESOLVE`). uv ≥0.13 `uv init --app` creates a `src/` package layout; services use a flat `app/` instead (no build-system).

- Tests: backend `pytest` needs `docker compose up` (infra); the suite drops/recreates `ai_companion_test` (`TEST_DATABASE_URL`, must end in `_test`) and runs migrations on it.

- Auth: Clerk dev instance configured (setup steps in README); webhook endpoint URL must include the `/webhooks/clerk` path. svix 2.x `Webhook.verify()` returns `None`; parse the body separately.

- Frontend: Next 16.4 + Clerk Core 3, both newer than most docs/training data. Read `frontend/node_modules/next/dist/docs/` and `@clerk/nextjs` types before using an API. Clerk dev instances answer cookie-less HTML requests with a handshake redirect (`dev-browser-missing`); curl checks need a cookie jar + `-L` first. In Git Bash, exported env values starting with `/` get rewritten to Windows paths (`/sign-in` → `C:/Program Files/Git/sign-in`); use `.env.local` or PowerShell (or `MSYS_NO_PATHCONV=1` for CLI args).

- Signed-in checks without a browser: Clerk Backend API (`CLERK_SECRET_KEY`) `sessions.createSession({userId})` → `sessions.getToken(id)` → request the frontend with `Authorization: Bearer <jwt>` (`clerkMiddleware` accepts header tokens); revoke the session after. Users created in Clerk get role `family` in the DB until the webhook delivers `user.updated`, so admin tests need the webhook (ngrok) or a manual DB role update. Dev-only: a non-admin opening `/admin` logs "Could not validate `instant`" (the layout redirect stops the child page from rendering); harmless.

- Browser E2E (used in REG-01b): run a prod frontend build against the real backend + Clerk dev. Sign test users in via Clerk sign-in tokens in headless Chrome. Sync their names/emails by delivering signed Clerk webhooks locally (`user.created`/`user.updated` signed with `CLERK_WEBHOOK_SECRET` the way `svix_headers` in `backend/tests/conftest.py` does, POSTed to `/webhooks/clerk`). Delete the test users and their data afterwards.

- Dograh infra: `DOGRAH_JWT_SECRET` missing from `infra/.env` makes every `docker compose` command fail, even `up -d postgres`. The `dograh-api` image has no `curl`/`wget`; check from inside it with `python -c "import urllib.request ..."`. Docker Desktop forwards `host.docker.internal` to the host's loopback, so `fastapi dev` (127.0.0.1) is reachable; on Linux `host-gateway` is the bridge IP, so the backend must listen on `0.0.0.0` (firewall port 8000) — not yet tested on Linux. `Error connecting to cloudflared` warnings in `dograh-api` logs are expected: the upstream quick tunnel (public URL for telephony webhooks) is left out. Dograh still looks up `cloudflared` on every health check, and a slow failing DNS lookup (~4s) made the UI show "Backend connection failed". Compose maps `cloudflared` to 127.0.0.1 so it fails instantly. This machine also has an old standalone `dograh` compose project (containers `dograh-*` + `minio`, volumes `dograh_*`); unused, and its ports clash if started.

- Dograh: pre-call hook times out after 10s; web calls need hook mode `Always` + a `caller_number` context variable; greetings need a fallback for missing variables. The tool test panel sends preset values as typed (no `{{initial_context.*}}` rendering): paste a real `session_token` from the hook.

- Dograh workflow: signing up on the self-host calls Dograh's cloud (managed service key, billing account, SIP), and the org default routes LLM/STT/TTS/embeddings through that managed connection. The DG-01b workflow overrides only the LLM (Gemini). Any saved change, Context Variables included, creates a draft: publish it. Edge labels become LLM function names (non-ASCII → `_`), so use ASCII `snake_case` labels. Text chat speaks only the greeting, and the prompt's first turn waits for the caller. Gemini free tier is 20 requests/day per model (each caller turn ≥ 1), enough for about one round of the text-chat tests.

- Windows shells: Git Bash also rewrites `docker exec` container paths and API path arguments (`/app/...`, `/auth/me`); prefix with `MSYS_NO_PATHCONV=1`. Python on the Windows console needs `PYTHONIOENCODING=utf-8` to print Vietnamese.
