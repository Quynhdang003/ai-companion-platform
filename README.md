# ai-companion-platform-
The AI chats with long-term memory, answers info questions (weather, news, daily life), performs tasks (ride booking, reminders, contacting family) and detects scam signs during calls, warning the user and alerting family.

## Structure

| Folder | Purpose |
|---|---|
| `backend/` | FastAPI business API (uv, Python 3.11+), SQLAlchemy + Alembic |
| `ride-sim/` | Standalone ride simulator service (FastAPI, uv) |
| `frontend/` | Next.js family + admin website |
| `infra/` | Docker Compose (PostgreSQL + pgvector) |
| `dograh/` | Dograh workflows, prompts, tool definitions |
| `context/` | Project specs (architecture, standards, progress) |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.11 automatically)
- Node.js 22+ and npm 11+
- Docker Desktop

## Setup

Copy each `.env.example` to `.env` (in `infra/`, `backend/`, `ride-sim/`; `.env.local` in `frontend/`) and fill in values.
For local dev, `infra/.env` with `postgres` / `postgres` / `ai_companion` / `5432` matches the backend's default `DATABASE_URL`.

```bash
cd backend  && uv sync
cd ride-sim && uv sync
cd frontend && npm install
```

### Clerk (web auth)

1. Create a Clerk application (development instance).
2. `backend/.env`: `CLERK_ISSUER` = the instance's Frontend API URL (e.g. `https://xxx.clerk.accounts.dev`; JWKS is read from `<issuer>/.well-known/jwks.json`).
3. Admins: set `{"role": "admin"}` in the user's **public metadata**. Everyone else is `family`.
4. Webhooks → add endpoint `<backend-url>/webhooks/clerk` with events `user.created`, `user.updated`, `user.deleted`. Locally, expose the backend with a tunnel (e.g. `ngrok http 8000`).
5. Copy the endpoint's signing secret (`whsec_...`) into `CLERK_WEBHOOK_SECRET`.

Users are also created (as `family`) on their first authenticated request, so sign-in works even before the webhook arrives.

## Run

```bash
# Database
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d

# Backend    -> http://localhost:8000/health
cd backend && uv run fastapi dev app/main.py --port 8000

# Ride simulator -> http://localhost:8001/health
cd ride-sim && uv run fastapi dev app/main.py --port 8001

# Frontend   -> http://localhost:3000
cd frontend && npm run dev
```

## Checks

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd backend  && uv run alembic current     # DB must be running
cd ride-sim && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run build
```
