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
- `pytest` tests for every service; mock external APIs. Tests that call a real external API are marked `live` and skipped by default (`uv run pytest -m live` runs them).
- LLM calls go through `LLMClient` (`app/llm/client.py`, `get_llm_client()`); services take it as a parameter, tests pass `FakeLLMClient` (`tests/fakes.py`). Routes get it with `Depends(get_llm_client)`; the test `client` fixture overrides it with `FakeLLMClient` (override again in a test for a specific fake).
  - Structured output: `generate_json(prompt, Schema)` returns the validated Pydantic model.
  - Embeddings: `embed(texts, task="document" | "query")`, always `EMBEDDING_DIMS` (`app/llm/embeddings.py`) long.
  - Errors: `LLMError`; `LLMRateLimitedError` (429, retry later); `LLMNotConfiguredError` (no `GEMINI_API_KEY`).
  - Scam classification uses `get_scam_llm_client()` (`GEMINI_SCAM_MODEL`), injected the same way; the test `client` fixture overrides it too.
  - On the real-time call path (Dograh tools), an LLM call runs against a deadline (`asyncio.wait_for`) and any `LLMError` or timeout falls back to a non-LLM answer: the tool never fails because of the LLM (`app/services/scam/engine.py`).
  - Prompts whose results are cached (`scripts.eval_scam`) carry a `PROMPT_VERSION`; bump it on any prompt change.
- Notifications go through `NotificationChannel` (`app/services/notification/channel.py`: `send(recipient, text)`, plain text). Errors: `NotificationError` (retry later); `RecipientUnreachableError` (e.g. the chat blocked the bot: stop sending to it). Telegram is `TelegramBot` (`telegram.py`, Bot API over httpx); tests use `FakeTelegramBot` (`tests/fakes.py`).
  - Bot API URLs contain the bot token: never log or raise a URL or a chained httpx error (`raise ... from None`); httpx's INFO request log is silenced.
  - Messages to family carry metadata and scam type/level only; logs never carry chat ids.
- Background jobs (pattern: `app/services/memory/job.py`):
  - A status column marks the queued work.
  - The job is registered in `app/core/scheduler.py` (APScheduler, started in the FastAPI lifespan; `SCHEDULER_ENABLED=false` turns it off).
  - Claim one row at a time with `FOR UPDATE SKIP LOCKED`, and write its results in a savepoint, so an error leaves nothing half-written.
  - LLM errors count as attempts, up to a max, then `failed`. Rate limits and a missing key don't count: the run stops and the row stays queued.
  - Jobs open sessions with a `SessionFactory` (`app/core/db.py`, default `SessionLocal`); tests pass `same_session(session)` (`tests/conftest.py`).
  - Tests call the per-row function directly with `FakeLLMClient`; the test client never starts the scheduler.

## TypeScript

- `strict` mode on; no `any` — use explicit types or narrow types.
- Validate external data (API responses, forms) with Zod.

## Next.js

- Server components by default; `use client` only for browser interaction.
- Clerk middleware protects `/dashboard/*` and `/admin/*` (in `proxy.ts`: Next 16 renamed `middleware.ts` to `proxy.ts`).
- `cacheComponents` is on: anything that reads the request (`auth()`, `getServerApi()`, Clerk `<Show>`, `<SignIn>`/`<SignUp>`) renders inside `<Suspense>`, never at a layout's top level. Exception: a gate that must decide before anything renders (the `/admin` role check) sits at the layout's top level with `export const instant = false`.
- Request-time client hooks (`usePathname`, `useSearchParams`) count as request data too: on dynamic routes (e.g. the `[[...sign-in]]` catch-all) they fail the prerender outside `<Suspense>`. Shared chrome takes such values as props instead (e.g. `PublicHero current="/demo"` for the active nav item).
- Backend calls go through one typed API client in `lib/api/` (`createApiClient`; `getServerApi()` on the server, `useApi()` in Client Components), attaching the Clerk token; responses parsed with Zod schemas in `lib/api/schemas.ts`, errors thrown as `ApiError` (`status`, `code`).
- Clerk Core 3 (`@clerk/nextjs` 7): `<SignedIn>`, `<SignedOut>` and `<Protect>` are removed; use `<Show when=...>`.
- Forms: React Hook Form + Zod; toasts via Sonner.

## Styling

- Use CSS tokens from `ui-context.md`; no hardcoded hex.
- Follow the radius scale in `ui-context.md`.

## API routes

- Validate and parse input before any logic.
- Check auth (JWT or API key) and ownership before any data mutation.
- Consistent response shape: success returns data; errors return `{ "error": { "code", "message" } }` with proper HTTP status.
- Dograh tool responses: short, speakable Vietnamese `message` + structured fields.
- New or changed routes (path, body, status codes, error codes) must be documented in `api-contracts.md`.

## Data and storage

- Metadata and business data in PostgreSQL.
- Recordings stay in Dograh; store URLs only.
- UUID primary keys with `server_default=gen_random_uuid()`.
- Enum-like columns as `VARCHAR` + named `CHECK` (SQLAlchemy `Enum(..., native_enum=False, create_constraint=True)`), not native PG enums.
- Constraint and index names follow the naming convention in `app/models/base.py` (`pk_`, `uq_`, `ix_`, `ck_`, `fk_`); migrations reference them by name.
- Rows owned by an elder or user use `ON DELETE CASCADE`; audit references (e.g. `decided_by`) use `SET NULL`.
- Phone numbers normalized to E.164 at the boundary, always via `normalize_vn_phone` (`app/services/identity/phone.py`; VN mobile + landline only); `elders.phone_e164` also has an E.164 `CHECK`.
- Store tokens hashed; never log tokens, phone numbers or transcripts in plain logs.
- Nullable JSONB columns use `JSONB(none_as_null=True)`: by default SQLAlchemy writes Python `None` as JSON `null`, which `IS NULL` doesn't match.
- Accent-free text search: generated columns and indexes call `immutable_unaccent()` (from the KB migration; `unaccent` itself isn't IMMUTABLE). In Python, `fold()` (`app/services/rag/search.py`) strips diacritics the same way.
- Hybrid search (`app/services/rag/search.py`): each ranking keeps only relevant rows (full-text word coverage, trigram threshold, max vector distance), then `rrf_merge` fuses them; the query embedding has a short timeout (`embed_query`) and falls back to lexical search. New searchable corpora reuse `words`, `fold`, `rrf_merge` and `embed_query`, and get thresholds calibrated with real embeddings.
  - Scam patterns (`app/services/scam/search.py`) are searched with a situation of a few sentences, not a question: phrase queries on word pairs (`word_pairs`, function words dropped) + vector, no trigram.
- Scam rules (`app/services/scam/rules.py`): phrases are matched accent-free on whole words, so each phrase must stay unambiguous once folded ("giữ bí mật", not "bí mật", which folds like "bị mất"). A new phrase that folds like an everyday word gets a look-alike test (`test_look_alike_words_are_not_signals`). A decisive rule must only fire on cases no legitimate caller produces; the test set (`backend/data/scam_eval/`) checks it. `Signal` codes live in `app/models/scam.py`: the rules, the classifier's output schema and stored scam events share them.
- Columns holding a scam type use `scam_type_column()` (`app/models/scam.py`), so every table shares the same values and its `CHECK` widens in one migration when a type is added.
- Seed data lives in `backend/data/`, loaded by a re-runnable script that skips unchanged rows (`scripts.seed_kb`; `scripts.seed_scam_patterns` embeds all new and changed patterns in one request).

## File organization

- `backend/app/api/` — routes (`web/`, `dograh/`, `webhooks/`).
- `backend/app/core/` — `config` (settings), `db` (async engine, `get_db()` / `DbSession`), `auth` (Clerk JWT, `CurrentUser`, `require_role`, `FamilyUser`), `dograh_auth` (`require_dograh_key`), `errors` (`AppError`, error shape).
- `backend/app/services/` — business modules.
- `backend/app/models/`, `backend/app/schemas/` — ORM models, Pydantic schemas.
- `backend/app/llm/` — Gemini client, prompts, output schemas.
- `backend/tests/` — pytest tests.
- `backend/scripts/` — maintenance scripts, run as `uv run python -m scripts.<name>`; `backend/data/` — sample data (KB documents).
- `ride-sim/app/` — simulator routes, pricing, dispatch, state machine.
- `frontend/app/` — routes; `frontend/components/` — feature components; `frontend/lib/` — API client, utils.
