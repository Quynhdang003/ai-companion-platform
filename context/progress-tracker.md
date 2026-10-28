# Progress Tracker

Update after every meaningful implementation change.

## Current phase

- Week 1 (plan: 4 weeks, ~5h/day).

## Current goal

- Week 1: environment, DB schema, Clerk, elder registration, pre-call hook, `session_token`, basic Dograh workflow.

## Completed

- `INF-01`: skeletons for `backend/` (FastAPI, uv, empty packages, pydantic-settings config, async Alembic init, no revisions), `ride-sim/` (FastAPI, uv), `frontend/` (Next.js 16 App Router, TS strict, Tailwind v4, shadcn/ui + sonner, Clerk/zod/RHF installed but not wired), `infra/docker-compose.yml` (PostgreSQL 17 + pgvector only), `dograh/` placeholder. Only `GET /health` on both Python services, one test each.
- `DB-01`: core schema `users`, `elders`, `elder_family`, `call_sessions` (models in `backend/app/models/`, migration `2799efe1c415`). UUID PKs (`gen_random_uuid()`), enum-like columns as `VARCHAR` + named `CHECK`, E.164 `CHECK` on `elders.phone_e164`, `ON DELETE CASCADE` from elders/users, `call_sessions.elder_id` nullable for unknown callers. `app/core/db.py` provides async engine + `get_db()`. Tests run against a real Postgres test DB.
- `AUTH-01` (backend): Clerk JWT verification via JWKS (`app/core/auth.py`: RS256, `iss`, `azp`, `CurrentUser`, `require_role`), user sync webhook `POST /webhooks/clerk` (Svix-verified; `user.created/updated` upsert role from `publicMetadata.role`, `user.deleted` removes user + family links), lazy user creation on first request, `GET /api/me`, global error shape `{"error": {"code", "message"}}` (`app/core/errors.py`), CORS. Tested with locally signed JWTs/webhooks, and verified live against the Clerk dev instance (webhooks via ngrok, real session tokens: 16/16 checks).
- `AUTH-02` (frontend): `ClerkProvider` (vi-VN via `@clerk/localizations`, accent color/font from tokens), `proxy.ts` requiring sign-in for `/dashboard/*` and `/admin/*`, `/sign-in` + `/sign-up` pages, typed API client (`lib/api/`: `createApiClient`, `getServerApi()`, Zod schemas, `ApiError`), `/dashboard` placeholder showing the role from `GET /api/me`, `/admin` placeholder whose layout checks the role before rendering (`instant = false`; non-admins get a 307 to `/dashboard`), shared `SiteHeader` with `UserButton`. Also wired the `ui-context.md` tokens into `globals.css` and switched the font to Be Vietnam Pro (`lang="vi"`). Verified against the Clerk dev instance + real backend: signed-out → 307 to `/sign-in` for all protected routes; family → `/dashboard` shows "Gia đình", `/admin` → 307 `/dashboard`; admin → `/admin` renders, `/dashboard` shows "Quản trị viên". Browser sign-in form and widget styling not checked by hand yet.
- `UI-01` (frontend): public pages from the `Demo.dc.html` design, brand renamed to "Touch the Light". Route group `app/(public)/` (URLs unchanged) holding `/` (landing: hero, how it works, CTA), new `/demo` (hotline + web-call cards, 3 scenario tabs with keyboard ←/→, risk bar, CTA) and `/sign-in`, `/sign-up`; shared `PublicHero`/`PublicHeader`/`PublicNav`/`PublicFooter`/`CtaBanner` in `components/public/`, `BrandLogo` also used by the dashboard `SiteHeader`. Derived color/gradient/shadow tokens + utilities in `globals.css` (documented in `ui-context.md`). Header account area streams in `<Suspense>` (`/` and `/demo` are partial prerender). `NEXT_PUBLIC_DEMO_PHONE_NUMBER` (unset → "Sắp ra mắt"). Verified with `npm run lint` + `npm run build` and headless Chrome at 1440px / 390px: all pages render, no horizontal overflow, no console errors, tabs switch by click and keyboard, signed-out `/dashboard` still 307 → `/sign-in`. Signed-in header state ("Trang quản lý" + `UserButton`) not checked in a browser yet.

## In progress

- None.

## Next

- Add Dograh and OSRM services to `infra/docker-compose.yml` (deferred from `INF-01`; do with the tasks that need them).
- Client-side API binding (`useAuth().getToken` → `createApiClient`) when the first client component needs the backend (likely `REG-01`).
- `REG-01`: elder registration form (E.164, duplicate → link request). Then point the public "Đăng ký cho người thân" CTAs at it for signed-in users (now `/sign-up`).
- Web call simulation page: point `/demo`'s "Mở trang gọi thử" at it (now `/dashboard`).
- Public "Tầm nhìn" / "Tài nguyên" pages from the design are hidden (no design files yet).
- Rename the Clerk application to "Touch the Light" in the Clerk Dashboard (the sign-in card still says "My Application").
- `ID-01`: pre-call hook + `session_token` + `confirm_activation` tool.

## Open questions

- STT/TTS provider: Azure Speech vs Google Chirp (decide after vi-VN quality/latency test).
- Embedding dims: 768 vs 1536.
- Geocoding: self-hosted Nominatim/Photon vs Goong API.
- Real telephony provider (if time allows) and its caller ID format.
- In-call scam check trigger: per turn vs every N turns.
- Data retention period for transcripts and recordings.
- Public demo hotline number for `/demo` (depends on real telephony), and whether the footer should name the university.
- Clerk deprecates `createRouteMatcher` (removed in its next major) in favor of auth checks in each page/layout. Kept for now: it gives clean 307s before rendering, and protected data is guarded by the backend anyway. Revisit when upgrading Clerk's major version.

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

- Tests: backend `pytest` needs `docker compose up` (infra); the suite drops/recreates `ai_companion_test` (`TEST_DATABASE_URL`, must end in `_test`) and runs migrations on it. Constraint names follow the naming convention in `app/models/base.py`.

- Auth: Clerk dev instance configured (setup steps in README); webhook endpoint URL must include the `/webhooks/clerk` path. svix 2.x `Webhook.verify()` returns `None`; parse the body separately. Without `CLERK_ISSUER` / `CLERK_WEBHOOK_SECRET` the endpoints return 500 `*_not_configured`.

- Frontend: Next 16.4 + Clerk Core 3, both newer than most docs/training data. Read `frontend/node_modules/next/dist/docs/` and `@clerk/nextjs` types before using an API. Clerk dev instances answer cookie-less HTML requests with a handshake redirect (`dev-browser-missing`); curl checks need a cookie jar + `-L` first. In Git Bash, exported env values starting with `/` get rewritten to Windows paths (`/sign-in` → `C:/Program Files/Git/sign-in`); use `.env.local` or PowerShell (or `MSYS_NO_PATHCONV=1` for CLI args).

- Signed-in checks without a browser: Clerk Backend API (`CLERK_SECRET_KEY`) `sessions.createSession({userId})` → `sessions.getToken(id)` → request the frontend with `Authorization: Bearer <jwt>` (`clerkMiddleware` accepts header tokens); revoke the session after. Users created in Clerk get role `family` in the DB until the webhook delivers `user.updated`, so admin tests need the webhook (ngrok) or a manual DB role update. Dev-only: a non-admin opening `/admin` logs "Could not validate `instant`" (the layout redirect stops the child page from rendering); harmless.

- Data: as of 2026-10-27 the Clerk dev instance has no users, but the DB still has one `admin` row (`user_3LE…`) from AUTH-01 whose `user.deleted` webhook never arrived.

- Dograh notes: pre-call hook 10s timeout, web calls need hook mode `Always` + `caller_number` context variable; greeting needs fallback for missing variables; verify `{{initial_context.*}}` rendering in tool test panel.
