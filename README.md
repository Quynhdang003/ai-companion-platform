# AI Companion Platform (Touch the Light)

Voice-first AI companion for elderly people (IT graduation thesis). The elder just calls: the AI greets registered callers by name, chats with long-term memory, answers questions from a knowledge base, books rides on a self-built simulator after a spoken yes, and detects scam signs during the call, warning the elder and alerting family on Telegram. Family members register the service and follow call activity on the website; admins manage the knowledge base.

## Status

All eight success criteria in `context/project-overview.md` are met and were re-checked on 2026-11-18 (`CHK-02`; criteria table and evidence in `context/progress-tracker.md`). Calls run as Dograh web calls; there is no phone number (real telephony was not added).

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
4. Admins: set `{"role": "admin"}` in the user's **public metadata**. Everyone else is `family`. The role reaches the database through the webhook (step 5); without a tunnel, set it there too (`UPDATE users SET role = 'admin' WHERE clerk_user_id = 'user_...';`). Admins manage the knowledge base at `/admin`.
5. Webhooks → add endpoint `<backend-url>/webhooks/clerk` with events `user.created`, `user.updated`, `user.deleted`. Locally, expose the backend with a tunnel (e.g. `ngrok http 8000`).
6. Copy the endpoint's signing secret (`whsec_...`) into `CLERK_WEBHOOK_SECRET`.

Users are also created (as `family`) on their first authenticated request, so sign-in works even before the webhook arrives.

### Dograh (voice platform)

`infra/docker-compose.yml` runs Dograh `1.50.0` (UI, API, plus its own Postgres, Redis and MinIO, separate from the app database).

1. `infra/.env`: set `DOGRAH_JWT_SECRET` (required, otherwise every `docker compose` command fails):
   `python -c "import secrets; print(secrets.token_hex(32))"`. Other `DOGRAH_*` variables are optional (see `infra/.env.example`).
2. Start the stack (images take ~3 GB on disk) and open the UI at http://localhost:3010. Create the first account, then set `DOGRAH_ENABLE_SIGNUP=false` and run `up -d` again (`restart` does not apply `.env` changes).
3. Dograh reaches the backend on the host at `http://host.docker.internal:8000`. On Linux, run the backend with `--host 0.0.0.0` (see Session notes in `context/progress-tracker.md`).
4. Create the credential, the nine HTTP tools and the workflow, then publish it: `dograh/README.md` (UI or API). The workflow export there is the source of truth for the prompts (v24).

| Service | URL (host) |
|---|---|
| Dograh UI | http://localhost:3010 |
| Dograh API | http://localhost:8010 (`/api/v1/health`) |
| Dograh MinIO | http://localhost:9000 (console 9001) |

### Telegram (family scam alerts)

1. In Telegram, message [@BotFather](https://t.me/BotFather): `/newbot`, pick a name and a username ending in `bot`.
2. `backend/.env`: `TELEGRAM_BOT_TOKEN` = the token BotFather gives, `TELEGRAM_BOT_USERNAME` = the username without `@`. Restart the backend (settings are read at start).
3. Family members connect on the dashboard ("Kết nối Telegram" → "Mở Telegram" → "Bắt đầu" in Telegram).

The backend fetches the bot's messages itself (`getUpdates`), so no public URL is needed; the bot must not have a webhook set (Bot API `deleteWebhook`). Only one backend process may poll a bot at a time. Without a token, connecting and the alerts are off and high-risk scam events stay `pending`.

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

# Sample scam patterns (backend/data/scam_patterns, one file per scam type; same rules)
cd backend && uv run python -m scripts.seed_scam_patterns

# Ride simulator -> http://localhost:8001/health (the backend's ride tools book through it,
# RIDE_SIM_BASE_URL; state in ride-sim/ride_sim.db;
# TIME_SCALE=30 in ride-sim/.env makes rides 30 times faster)
cd ride-sim && uv run fastapi dev app/main.py --port 8001

# Ride simulator faults while it runs (no_driver, driver_cancels, timeout, price_surge; null = off)
curl -X PATCH localhost:8001/sim/config -H 'Content-Type: application/json' -d '{"fault": "no_driver"}'

# Frontend   -> http://localhost:3000
cd frontend && npm run dev
```

## Before a demo

- **Gemini quota.** The free tier allows 20 requests a day per model, and memory extraction uses one per call (more if it retries). It resets at 15:00 Vietnam time. Keep test calls away from the demo, or use a paid key: without quota, memories of new calls wait, and the next call can't recall them.
- **Dograh.** The published workflow is v24, and the web call's `caller_number` Context Variable is the number of the elder you play (`dograh/README.md`, "Voice web calls").
- **Ride simulator.** No fault set and `time_scale` 1: `curl localhost:8001/sim/config`.
- **Telegram.** The family member connected Telegram on the dashboard, and only one backend process runs (it polls the bot).

## Checks

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd backend  && uv run alembic current     # DB must be running
cd ride-sim && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd ride-sim && uv run pytest -m live       # public OSRM and Photon, network needed
cd frontend && npm run lint && npm run build
```

Map data: routes from OSRM and places from Photon, both on OpenStreetMap data (© OpenStreetMap contributors, ODbL); the built-in Hanoi places in `ride-sim/app/data/hanoi_places.json` come from the same source.
