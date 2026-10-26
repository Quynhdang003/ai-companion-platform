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
