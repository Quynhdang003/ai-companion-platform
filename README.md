# ai-companion-platform-
The AI chats with long-term memory, answers info questions (weather, news, daily life), performs tasks (ride booking, reminders, contacting family) and detects scam signs during calls, warning the user and alerting family.

## Structure

| Folder | Purpose |
|---|---|
| `backend/` | FastAPI business API (uv, Python 3.11+), SQLAlchemy + Alembic |
| `ride-sim/` | Standalone ride simulator service (FastAPI, uv) |
| `frontend/` | Next.js family + admin website |
| `infra/` | Docker Compose (PostgreSQL + pgvector, self-hosted Dograh) |
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
3. `frontend/.env.local`: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` from the **same** instance (Dashboard → API keys). Without them `next dev` runs Clerk in keyless mode on a temporary instance, whose tokens the backend rejects.
4. Admins: set `{"role": "admin"}` in the user's **public metadata**. Everyone else is `family`.
5. Webhooks → add endpoint `<backend-url>/webhooks/clerk` with events `user.created`, `user.updated`, `user.deleted`. Locally, expose the backend with a tunnel (e.g. `ngrok http 8000`).
6. Copy the endpoint's signing secret (`whsec_...`) into `CLERK_WEBHOOK_SECRET`.

Users are also created (as `family`) on their first authenticated request, so sign-in works even before the webhook arrives.

### Dograh (voice platform)

`infra/docker-compose.yml` runs Dograh `1.50.0` (UI, API, plus its own Postgres, Redis and MinIO, separate from the app database).

1. `infra/.env`: set `DOGRAH_JWT_SECRET` (required, otherwise every `docker compose` command fails):
   `python -c "import secrets; print(secrets.token_hex(32))"`. Other `DOGRAH_*` variables are optional (see `infra/.env.example`).
2. Start the stack (images take ~3 GB on disk) and open the UI at http://localhost:3010. Create the first account, then set `DOGRAH_ENABLE_SIGNUP=false` and run `up -d` again (`restart` does not apply `.env` changes).
3. Dograh reaches the backend on the host at `http://host.docker.internal:8000`. On Linux, run the backend with `--host 0.0.0.0` (see Session notes in `context/progress-tracker.md`).

| Service | URL (host) |
|---|---|
| Dograh UI | http://localhost:3010 |
| Dograh API | http://localhost:8010 (`/api/v1/health`) |
| Dograh MinIO | http://localhost:9000 (console 9001) |

## Run

```bash
# PostgreSQL + Dograh (or `up -d postgres` for the database only)
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d

# Backend reachable from Dograh (inside the dograh-api container)
docker compose -f infra/docker-compose.yml --env-file infra/.env exec dograh-api \
  python -c "import urllib.request as u; print(u.urlopen('http://host.docker.internal:8000/health').read())"

# Backend    -> http://localhost:8000/health
cd backend && uv run fastapi dev app/main.py --port 8000

# Sample knowledge-base documents (backend/data/kb, needs GEMINI_API_KEY; safe to re-run)
cd backend && uv run python -m scripts.seed_kb

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
