# Architecture

## Stack

| Layer | Technology | Role |
|---|---|---|
| Voice | Dograh (self-host) | Calls, pre-call hook, HTTP tools, end-of-call webhook |
| STT/TTS | Azure Speech or Google Chirp (vi-VN), configured in Dograh | Vietnamese speech |
| Conversation LLM | Gemini Flash (in Dograh) | Real-time dialogue, tool calling |
| Analysis LLM | Gemini, JSON output + Pydantic | Scam classification, memory extraction |
| Embedding | Gemini Embedding, fixed dims | Memory + KB vectors |
| Backend | Python + FastAPI, SQLAlchemy 2 + Alembic, APScheduler | Business API, hooks, tools, jobs |
| Ride Simulator | FastAPI + OSRM + Nominatim/Photon (or Goong) | Simulated ride provider over REST |
| Database | PostgreSQL + pgvector (HNSW), `unaccent`, `pg_trgm` | Data, memory, vectors, hybrid search |
| Frontend | Next.js + React + TypeScript | Family + admin website |
| UI | Tailwind CSS + shadcn/ui | Components, styling |
| Auth | Clerk | Web login, roles `family`/`admin` |
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
- `infra/` — Docker Compose, OSRM/geocoder data setup.

## Storage model

- **PostgreSQL**: users (role + display name/email synced from the Clerk webhook), elders, family links, link requests, call sessions, call logs + summaries, memories (text + vector), KB chunks (text + vector + tsvector), scam patterns, scam events, reminders, ride bookings.
- **Dograh**: recordings and raw transcripts (backend stores URLs + processed transcript).
- **Clerk**: credentials and sessions only; business data stays in PostgreSQL.
- **Ride Simulator DB/state**: drivers, trips (separate from backend DB).

## Auth and access model

- Family/admin log in via Clerk; FastAPI verifies JWT via JWKS; role from `publicMetadata`; users synced via Clerk webhook (`clerk_user_id`); a verified user missing from the DB is created as `family` on first request (webhook stays source of truth for role).
- Website: `proxy.ts` requires a Clerk session for `/dashboard/*` and `/admin/*`; the `/admin` layout also checks the role via `GET /api/me` before rendering and redirects non-admins to `/dashboard` (navigation only; the backend enforces roles). The role shown on the website always comes from the backend DB, not Clerk metadata.
- Elderly have no account: identified by `from_number` (E.164) in pre-call hook; must be `ACTIVE` (consent given) to access personal data.
- Each call gets a `call_session` with an expiring `session_token` (stored hashed); all Dograh tools resolve `elder_id` from it.
- Family access to elder data only via `elder_family` link (`owner` manages, `viewer` reads). Registering a taken number creates an `elder_link_requests` row instead; only the owner can approve (requester becomes `viewer`) or reject, and the requester sees no elder data until approved. Elder registration and link requests are family-only routes. Admin manages KB and scam patterns only.

## Invariants

1. The LLM never supplies `elder_id`, phone numbers or user identifiers; identity comes only from `session_token`.
2. Dograh-facing endpoints require API key; web endpoints require Clerk JWT + `elder_family` check.
3. Pre-call hook stays < 500ms and always returns valid JSON; no LLM calls in it.
4. Post-call work (memory extraction, summaries, embeddings) runs async, never blocks webhook response.
5. Sensitive tools (`book_ride`, `cancel_ride`, `contact_family`, profile changes) execute only after explicit verbal confirmation.
6. All LLM structured output is validated with Pydantic before storage or action.
7. Phone numbers are stored only in E.164; one `elder` per number.
8. Embedding model and dimensions are fixed; changing them requires full re-index.
