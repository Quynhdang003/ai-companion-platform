# AI Companion Platform – Voice assistant supporting and protecting the elderly from scams

## Overview

Voice-first AI companion (not a chatbot) for lonely elderly people. Elderly users need no smartphone, app or account: they just call the system's number. The AI chats with long-term memory, answers info questions (weather, news, daily life), performs tasks (ride booking, reminders, contacting family) and detects scam signs during calls, warning the user and alerting family. Family members use a website to register the service and monitor usage; admins manage the knowledge base. IT graduation thesis: focus on AI application design, context management and personalization, no model training.

## Goals

1. Identify registered elderly callers by phone number and greet them by name (pre-call hook < 500ms).
2. Remember info across calls and reuse it in context (e.g. "same as last time" → home → Bach Mai Hospital).
3. Detect scams in-call (impersonating police/bank/grandchildren, investment, health supplements, resort contracts, fake charity), warn the user, alert family via Telegram on high risk.
4. Execute tasks via tool calling, always with verbal confirmation before sensitive actions.
5. Let family register, manage profiles and view call history on the website.

## Core user flows

### A – Family registers service

1. Family signs in (Clerk), fills form: full name + phone (required), other info optional.
2. Backend normalizes phone to E.164 (`0912345678` → `+84912345678`):
   - New number → create `elder` with `status = PENDING_VERIFICATION`, link family as `owner`.
   - Existing number → no new record; send link request for the current `owner` to approve.
3. On the first call from that number, AI asks for consent → tool `confirm_activation` → `ACTIVE`, store `consent_at`.

### B – Elderly user calls

1. Call reaches Dograh → pre-call hook `POST /hooks/pre-call` `{from_number, to_number, agent_id}` + API key.
2. Backend verifies key, normalizes number, looks up `elders`, creates `call_session` + `session_token`.
3. Returns `initial_context`:
   - `ACTIVE`: name, preferred name, memory summary, frequent places, `session_token`.
   - `PENDING_VERIFICATION`: registering family name, `session_token` (AI asks consent).
   - Unknown/blocked: `is_registered: false`, generic greeting, no personal data.
4. All HTTP tools send `session_token` via Preset Parameter `{{initial_context.session_token}}`; backend resolves `elder_id`.
5. Scam Risk Engine scores each turn; high risk → AI warns + Telegram alert to family.
6. End-of-call webhook (transcript, linked via `workflow_run_id`) → async memory extraction + call summary.

### C – Ride booking

1. AI collects pickup, destination, time, ride type (uses memory).
2. `search_location` → `get_ride_quote` → AI reads price/ETA.
3. User confirms verbally → `book_ride`. Then `get_ride_status` / `cancel_ride`; family notified.

## Modules

- **Companion Agent**: real-time Vietnamese voice chat, elderly-friendly tone; orchestrator routes requests (chat / info / task / safety).
- **Memory Manager**: post-call extraction with Gemini JSON output + Pydantic; embedded memories; summary served in pre-call hook.
- **RAG Agent**: KB (elderly support, services, safety, scam knowledge); hybrid search (PG full-text `simple` + `unaccent` + `pg_trgm` + pgvector, RRF).
- **Scam Risk Engine**: layer 1 rules/keywords; layer 2 Gemini classification with retrieved scam patterns → JSON `{risk_level, scam_type, signals, reason}`.
- **Task Agent**: tools `search_location`, `get_ride_quote`, `book_ride`, `get_ride_status`, `cancel_ride`, `contact_family`, reminders, weather; `RideProvider` interface → Ride Simulator over REST.
- **Ride Simulator** (separate FastAPI service): OSRM routing; Nominatim/Photon (or Goong) geocoding; pricing (base + per km + per min by ride type, peak multiplier); fake drivers seeded around Hanoi; state machine `REQUESTED → DRIVER_ASSIGNED → ARRIVING → IN_PROGRESS → COMPLETED/CANCELLED` computed from timestamps; `time_scale`, fixed `seed`, fault injection (no driver, driver cancels, timeout, price surge). API: `POST /quotes`, `POST /bookings`, `GET /bookings/{id}`, `POST /bookings/{id}/cancel`, `GET /places/search`.
- **Notification Service**: `NotificationChannel` interface; Email (reports) + Telegram Bot (urgent alerts).
- **Family website**: auth, register elder, manage profile, call history (summary, duration, scam alerts), notification settings, web call simulation.
- **Admin website**: manage KB documents (auto embed/index) and scam patterns.

## Scope

**In:** Dograh calls (web-simulated; real telephony if time allows, same AI architecture); all backend modules above; self-built Ride Simulator; family + admin websites; phone-number identity with consent activation.

**Out:** model training/fine-tuning; real ride platforms (Grab, Be, Xanh SM, Uber) and Karhoo Sandbox; real payments, paid subscription (only if time allows); mobile app; Zalo ZNS; Elasticsearch, Vietnamese word segmentation; telecom-level caller ID anti-spoofing (mitigated by verbal confirmation, documented as limitation).

## Tech stack

| Component | Technology |
|---|---|
| Voice | Dograh (self-host) |
| STT/TTS | Azure Speech or Google Cloud Speech (Chirp), vi-VN, configured in Dograh |
| Conversation LLM | Gemini Flash (in Dograh) |
| Analysis LLM | Gemini, JSON structured output + Pydantic |
| Embedding | Gemini Embedding, fixed dims (768 or 1536) |
| Backend | Python + FastAPI, SQLAlchemy 2 + Alembic, APScheduler |
| Database | PostgreSQL + pgvector (HNSW) |
| Search | Hybrid full-text + vector (RRF) |
| Notification | Email + Telegram Bot |
| Frontend | Next.js + React + TypeScript, Tailwind + shadcn/ui, calls FastAPI directly |
| Web auth | Clerk; FastAPI verifies JWT via JWKS; roles `family`/`admin` in `publicMetadata`; user sync via webhook |
| Dograh ↔ Backend | API key (Bearer) + per-call `session_token` |
| Deploy | Vercel (frontend) + VPS Docker Compose (Dograh, FastAPI, Ride Simulator, OSRM, PostgreSQL) |

**Core tables:** `users(id, clerk_user_id, role)`, `elders(id, phone_e164 UNIQUE, full_name, preferred_name, status, consent_at, profile JSONB)`, `elder_family(elder_id, user_id, role, created_at)`, `call_sessions(id, elder_id, session_token_hash, workflow_run_id, from_number, started_at, expires_at)`.

## Agent rules

- Never let the LLM supply `elder_id`, phone numbers or user identifiers as tool params; always resolve from `session_token`.
- Dograh-facing endpoints verify API key; website endpoints verify Clerk JWT and check access via `elder_family`.
- Pre-call hook: fast (< 500ms), always valid JSON; Dograh greeting needs a fallback for missing variables.
- Sensitive actions (`book_ride`, `cancel_ride`, `contact_family`, profile changes) require verbal confirmation first.
- Keep `initial_context` minimal; fetch detailed health notes via tools only when needed.
- Modular plain Python/FastAPI; no Celery, Elasticsearch or LangChain unless necessary.

## Success criteria

1. Logged-in family can register an elder by name + phone; duplicate numbers become link requests.
2. First call from a `PENDING_VERIFICATION` number asks consent; on yes → `ACTIVE` + `consent_at`.
3. `ACTIVE` callers are greeted by name within 2s of connecting; unknown numbers get a generic greeting with no personal data.
4. Info from a previous call is correctly recalled in a later call.
5. On a test set covering all 6 scam types, high-risk scenarios are flagged, the AI warns in-call and family gets a Telegram alert.
6. Voice ride booking works via quote → confirm → book; `book_ride` never runs without confirmation; simulator fault cases are handled and reported to the user.
7. Family sees call history only for elders they manage.
8. Admin adds a KB document and the AI answers questions from it.