# Architecture

## Stack

| Layer | Technology | Role |
|---|---|---|
| Voice | Dograh 1.50.0 (self-host, Docker images) | Calls, pre-call hook, HTTP tools, end-of-call webhook |
| STT/TTS | Dograh-managed (vi-VN, voice "Ngoc"), configured in Dograh | Vietnamese speech |
| Conversation LLM | Dograh-managed (model `default`), configured in Dograh | Real-time dialogue, tool calling |
| Analysis LLM | Gemini, JSON output + Pydantic | Scam classification, memory extraction |
| Embedding | `gemini-embedding-001`, 768 dims | Memory + KB vectors |
| Backend | Python + FastAPI, SQLAlchemy 2 + Alembic, APScheduler | Business API, hooks, tools, jobs |
| Ride Simulator | FastAPI + OSRM + Nominatim/Photon (or Goong) | Simulated ride provider over REST |
| Database | PostgreSQL 17 + pgvector (HNSW), `unaccent`, `pg_trgm` | Data, memory, vectors, hybrid search |
| Frontend | Next.js 16 (App Router) + React 19 + TypeScript | Family + admin website |
| UI | Tailwind CSS v4 (CSS-first config in `globals.css`, no `tailwind.config`) + shadcn/ui | Components, styling |
| Auth | Clerk Core 3 (`@clerk/nextjs` 7) | Web login, roles `family`/`admin` |
| Notification | Email + Telegram Bot | Reports, urgent scam alerts |
| Deploy | Vercel + VPS Docker Compose | Hosting |

## System boundaries

- `backend/app/api/` — HTTP routes: `web/` (Clerk JWT), `dograh/` (API key: pre-call hook, tools, webhook), `webhooks/` (Clerk).
- `backend/app/services/` — Business modules: `companion`, `memory`, `rag`, `scam`, `task`, `ride`, `notification`, `conversation`, `identity`.
- `backend/app/models/` — SQLAlchemy models; `backend/alembic/` — migrations.
- `backend/app/llm/` — Gemini client, prompts, Pydantic output schemas, embeddings.
- `ride-sim/` — Standalone ride simulator; backend accesses it only via `RideProvider` adapter over HTTP.
- `frontend/` — Next.js website; calls backend REST only, never the DB.
- `dograh/` — Exported workflows, prompts, tool definitions (docs/config, not code).
- `infra/` — Docker Compose (app PostgreSQL; Dograh UI, API and its own Postgres/Redis/MinIO), OSRM/geocoder data setup. Dograh services sit on a separate `dograh` network: they can't reach the app database and talk to the backend only over HTTP (`host.docker.internal`: pre-call hook, tools, end-of-call webhook). The backend calls Dograh only to download transcripts from its public download links (`DOGRAH_BASE_URL`, Dograh's `BACKEND_API_ENDPOINT`). Host ports: backend 8000, ride-sim 8001, frontend 3000, app PostgreSQL 5432, Dograh UI 3010 / API 8010 / MinIO 9000-9001 (Dograh ports on localhost only).

## Storage model

- **PostgreSQL**: users (role + display name/email synced from the Clerk webhook), elders, family links, link requests, call sessions, call logs (one per call session: duration, disposition, processed transcript + recording link for consented callers, memory extraction status), memories (per elder: category, subject, one short Vietnamese sentence, importance, mention count, vector; extracted from transcripts by a background job), KB documents (full text kept for re-indexing) and their chunks (≤ 800 chars, accent-free tsvector, trigram index, vector), scam patterns, scam events, reminders, ride bookings.
- **Dograh**: recordings and raw transcripts (backend stores URLs + processed transcript), in Dograh's own Postgres + MinIO; never shared with the app database.
- Conversation content (transcripts, memories) is read only by backend jobs and the AI (pre-call hook, tools); no web route returns it.
- **Clerk**: credentials and sessions only; business data stays in PostgreSQL.
- **Ride Simulator DB/state**: drivers, trips (separate from backend DB).

## Auth and access model

- Family/admin log in via Clerk; FastAPI verifies JWT via JWKS (RS256, `iss`, `azp`); role from `publicMetadata`; users synced via Clerk webhook (`clerk_user_id`); a verified user missing from the DB is created as `family` on first request (webhook stays source of truth for role). `user.deleted` removes the user and their family links (and link requests); the elders stay.
- Website: `proxy.ts` requires a Clerk session for `/dashboard/*` and `/admin/*`; the `/admin` layout also checks the role via `GET /api/me` before rendering and redirects non-admins to `/dashboard` (navigation only; the backend enforces roles). The role shown on the website always comes from the backend DB, not Clerk metadata.
- Elderly have no account: identified by `from_number` (E.164) in pre-call hook; must be `ACTIVE` (consent given) to access personal data.
- Dograh calls `/hooks/*` and `/tools/*` with `Authorization: Bearer <DOGRAH_API_KEY>` (compared in constant time).
- Each call gets a `call_session` with an expiring `session_token` (`secrets.token_urlsafe(32)`, SHA-256 hash stored, TTL `SESSION_TOKEN_TTL_MINUTES`, default 120); all Dograh tools resolve `elder_id` from it. One session per `workflow_run_id`: a retried pre-call hook rotates the token. Unknown and blocked callers, and invalid or empty caller numbers, get a session with no `elder_id`, so tools can't reach any elder's data. Tools over shared, non-personal data (KB search) accept any live session. Dograh keeps the raw token in its own run record (`initial_context`), but tool calls also need the API key, so the token alone grants nothing.
- Family access to elder data only via `elder_family` link (`owner` manages, `viewer` reads); for calls, family sees metadata and scam alerts only. Registering a taken number creates an `elder_link_requests` row instead (at most one pending request per requester and elder); only the owner can approve (requester becomes `viewer`) or reject, and the requester sees no elder data until approved. Elder registration and link requests are family-only routes. Admin manages KB and scam patterns only.

## Invariants

1. The LLM never supplies `elder_id`, phone numbers or user identifiers; identity comes only from `session_token`.
2. Dograh-facing endpoints require API key; web endpoints require Clerk JWT + `elder_family` check.
3. Pre-call hook stays < 500ms and always returns valid JSON; no LLM calls in it.
4. Post-call work (memory extraction, scam analysis, embeddings) runs async, never blocks webhook response: the webhook only stores a status (e.g. `call_logs.memory_status = pending`) that an APScheduler job picks up.
5. Sensitive tools (`book_ride`, `cancel_ride`, `contact_family`, profile changes) execute only after explicit verbal confirmation.
6. All LLM structured output is validated with Pydantic before storage or action.
7. Phone numbers are stored only in E.164; one `elder` per number.
8. Embedding model and dimensions are fixed; changing them requires full re-index.
9. Web routes never return transcripts or memories; family alerts carry scam type, risk level and time only.
