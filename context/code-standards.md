# Code Standards

## General

- Small, single-purpose modules; plain Python/FastAPI, no heavy frameworks (no Celery, LangChain, Elasticsearch).
- Fix root causes, no stacked workarounds.
- Don't mix unrelated concerns in one module, route or component.
- Config via env vars (`pydantic-settings`); secrets never committed.

## Python (backend, ride-sim)

- Python 3.11+, full type hints; `ruff` for lint/format.
- Pydantic models for all request/response bodies and LLM outputs.
- Routes stay thin: validate → call service → return. Logic lives in `services/`.
- External services (Gemini, ride provider, notification channels) behind interfaces (`RideProvider`, `NotificationChannel`, LLM client) for mocking in tests.
- Async DB access with SQLAlchemy 2; schema changes only via Alembic migrations.
- `pytest` tests for every service; mock external APIs.

## TypeScript

- `strict` mode on; no `any` — use explicit types or narrow types.
- Validate external data (API responses, forms) with Zod.

## Next.js

- Server components by default; `use client` only for browser interaction.
- Clerk middleware protects `/dashboard/*` and `/admin/*`.
- Backend calls go through one typed API client in `lib/api/`, attaching the Clerk token.
- Forms: React Hook Form + Zod; toasts via Sonner.

## Styling

- Use CSS tokens from `ui-context.md`; no hardcoded hex.
- Follow the radius scale in `ui-context.md`.

## API routes

- Validate and parse input before any logic.
- Check auth (JWT or API key) and ownership before any data mutation.
- Consistent response shape: success returns data; errors return `{ "error": { "code", "message" } }` with proper HTTP status.
- Dograh tool responses: short, speakable Vietnamese `message` + structured fields.

## Data and storage

- Metadata and business data in PostgreSQL.
- Recordings stay in Dograh; store URLs only.
- Phone numbers normalized to E.164 at the boundary.
- Store tokens hashed; never log tokens, phone numbers or transcripts in plain logs.

## File organization

- `backend/app/api/` — routes (`web/`, `dograh/`, `webhooks/`).
- `backend/app/services/` — business modules.
- `backend/app/models/`, `backend/app/schemas/` — ORM models, Pydantic schemas.
- `backend/app/llm/` — Gemini client, prompts, output schemas.
- `backend/tests/` — pytest tests.
- `ride-sim/app/` — simulator routes, pricing, dispatch, state machine.
- `frontend/app/` — routes; `frontend/components/` — feature components; `frontend/lib/` — API client, utils.
