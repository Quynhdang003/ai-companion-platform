# Progress Tracker

Update after every meaningful implementation change.

## Current phase

- Week 3 (plan: 4 weeks, ~5h/day). Week 1 finished 2026-11-07, Week 2 (memory across calls, knowledge base search) finished 2026-11-09.

## Current goal

- Week 3: scam detection during calls (criterion 5). The agent calls `check_scam` when the caller tells it about a suspicious call or request. A two-layer engine (rules, then Gemini with retrieved scam patterns) returns a spoken warning; on high risk the elder's family gets a Telegram alert (type, level, time only). Reuses the hybrid search helpers (`app/services/rag/search.py`) and the background job pattern (`app/services/memory/job.py`).

## Completed

| ID | Summary | Verified |
|---|---|---|
| `INF-01` | Skeleton backend, ride-sim, frontend; compose PostgreSQL + pgvector | `/health` tests |
| `DB-01` | Core schema: users, elders, elder_family, call_sessions (`2799efe1c415`) | pytest on real PG |
| `AUTH-01` | Clerk JWT via JWKS, user sync webhook, `GET /api/me`, error shape | Live vs Clerk dev |
| `AUTH-02` | ClerkProvider vi-VN, `proxy.ts`, typed API client, role-gated `/admin` | Live vs Clerk dev |
| `UI-01` | Public pages `/`, `/demo`, sign-in/up (Touch the Light branding) | Headless Chrome 1440/390 |
| `REG-01a` | Elder registration + link requests with owner approval (`8c9a52a4bb0d`) | 77 tests |
| `REG-01b` | Dashboard: register form, elder list, approve/reject requests | E2E, 2 Clerk users |
| `ID-01` | Pre-call hook, `session_token`, `confirm-activation` tool | 107 tests |
| `DG-01a` | Self-hosted Dograh 1.50.0 in compose, own Postgres/Redis/MinIO, backend reachable from it | Healthchecks; container → host `/health` 200 |
| `DG-01b` | Dograh identity + consent workflow, `confirm_activation` tool, exports in `dograh/` | Text chat (Gemini): active, pending → ACTIVE, unknown |
| `UI-02` | Public copy: family sees call time/duration only, no call summaries | Lint + build; `/`, `/demo` at 1440/390 |
| `CALL-01a` | End-of-call webhook `/hooks/call-ended` → `call_logs` (`87d572f79894`); transcript for consented callers only | 134 tests; real Dograh transcript format |
| `CALL-01b` | Dograh Webhook node → `/hooks/call-ended` (workflow v13), export in `dograh/` | Text chat: ACTIVE → transcript, unknown → metadata only; deliveries `succeeded` |
| `LLM-01` | Gemini client (`app/llm/`): JSON output validated by Pydantic, 768-dim embeddings, fake for tests | Mocked-HTTP tests; live smoke (`pytest -m live`) vs Gemini |
| `MEM-01` | `memories` (`45022702e0a4`) + post-call extraction job (APScheduler, Gemini → Pydantic → embed) | Tests; voice call → 3 memories 26 s after the call ends; category fix checked by a rolled-back re-run |
| `MEM-02a` | Pre-call hook adds `memory_summary` + `frequent_places` for ACTIVE callers (no LLM) | 174 tests; hook 9–13 ms warm (105 ms cold) with 100 memories |
| `MEM-02b` | Dograh prompt uses the memory keys (workflow v14) | Criterion 4 by voice: call 2 recalled the back pain and Bạch Mai |
| `RAG-01` | KB documents/chunks (`29dd51ed62b1`), hybrid search (full-text + trigram + vector, RRF), 3 sample docs + seed | 203 tests; real embeddings: 6/6 related questions → right doc, 2/2 unrelated → nothing |
| `RAG-02a` | Tool `POST /tools/search-knowledge`: top 3 KB chunks for any live call | 215 tests; dev backend, real embeddings: emergency/OTP/cost questions → right doc, gold price → nothing; 0.4–0.75 s |
| `RAG-02b` | Dograh `search_knowledge` tool + prompt for every caller (workflow v16) | Text chat, ACTIVE + unknown: 115, OTP, cost/features from KB; gold price not invented; tool 0.5–0.8 s. Voice check skipped (user decision) |
| `SCAM-01` | Scam types, `scam_patterns` (`4b3ed2a15c4a`) + 27 seed patterns, hybrid search (word pairs + vector, RRF) | 247 tests; real embeddings: 16/16 situations → right type first, 4/5 one-liners, 3/3 unrelated → nothing |
| `SCAM-02` | Labelled test set (53 cases) + layer-1 rules: 21 signals, 8 decisive rules, type from weighted cues | 381 tests; on the set: 22/35 high decisive, 0 decisive on non-high, every high ≥ medium, every none ≤ low (optimistic: rules and set written together) |
| `SCAM-03` | Layer 2 (Gemini on its own model) + engine: decisive rule skips it, failures fall back to rules; `scripts.eval_scam` | 404 tests; live on 34/53 cases (`gemini-3.5-flash-lite`, free-tier quota): 31/34 high → high (rules alone 22/35), 34/34 warned with the right type; 3 transient errors fell back to rules; classifier p50 2.1 s, p90 3.8 s (budget 4 s) |

## In progress

- None.

## Next

- `SCAM-03b`: finish the live eval (`uv run python -m scripts.eval_scam`, resumes from its cache): 19 cases left (`other-04` and every medium, low and none case), so the classifier's false alarms on look-alikes are still unmeasured. Also see whether the transient classifier errors repeat (now logged).
- `SCAM-04a`: `scam_events` table + tool `POST /tools/check-scam` `{session_token, situation}`. Every caller gets a templated spoken warning. For ACTIVE elders it stores type, level and signal codes (no call text); high risk → `alert_status = pending`.
- `SCAM-04b`: Dograh `check_scam` tool + prompt (when to call it, how to warn), workflow v17; text chat: one case per type + benign cases.
- `NOTI-01a`: `NotificationChannel` + Telegram bot channel. Family members link Telegram with a one-time deep link (`/start <token>`, read by a `getUpdates` polling job, no public URL needed); routes to link, check status, unlink.
- `NOTI-01b`: dashboard card to connect and disconnect Telegram.
- `NOTI-02`: alert job: pending high-risk events → Telegram to every linked family member who connected it (elder name, type, level, time; one alert per call and type); retries, then `failed`. End-to-end: a scam case in text chat → Telegram on a phone (criterion 5).
- `SCAM-05` (if time allows): post-call scan of stored transcripts, a safety net for scams the agent didn't check in the call; alerts only if that call has no alert of the same type yet.

## Backlog (unscheduled)

- Admin KB page: add and manage KB documents, embedded and indexed on save (the admin half of criterion 8; reuses `app/services/rag/ingest.py`). To be planned.
- Admin scam patterns page: add and edit patterns per scam type (reuses `sync_patterns` in `app/services/scam/patterns.py`). To be planned with the admin KB page.
- OSRM service in `infra/docker-compose.yml`, with the ride units.
- Web call simulation page; point `/demo` "Mở trang gọi thử" at it.
- Public "Tầm nhìn" / "Tài nguyên" pages (waiting for design).

## Open questions

- Geocoding: self-hosted Nominatim/Photon vs Goong API.
- Real telephony provider (if time allows) and its caller ID format.
- Data retention period for transcripts and recordings.
- Public demo hotline number for `/demo` (depends on real telephony), and whether the footer should name the university.
- Orphaned elders: if an owner deletes their account, the elder stays but pending link requests have nobody to approve them.
- Link request notifications: owners only see requests on the dashboard until the Notification Service exists.

## Architecture decisions

- Clerk for web auth: fast integration, business data kept in PostgreSQL.
- Elder identity by phone + consent activation on first call: no account needed, records consent.
- Per-call `session_token` via Preset Parameter: LLM can't spoof identity.
- Self-built Ride Simulator, no Karhoo: no third-party dependency, full test control.
- Hybrid search in PostgreSQL: no extra infra, tolerant to STT errors.
- KB search open to every live call, unknown and pending-consent callers included: the KB holds no personal data, and callers can ask about the service before consenting.
- Embeddings: `gemini-embedding-001` at 768 dims for memories and KB: smaller HNSW index, enough for short Vietnamese text. Changing it means a full re-index.
- Telegram for urgent alerts, Email for reports: email too slow for scam alerts.
- Scam check split: real-time in-call + async post-call memory extraction.
- In-call scam check is a tool the agent calls (`check_scam`), not a per-turn check: Dograh 1.50.0 has no per-turn backend hook (node types: `startCall`, `agentNode`, `endCall`, `globalNode`, `webhook`, `trigger`, `qa`). The agent calls it when the caller tells it about a suspicious call or request; the post-call scan (`SCAM-05`) catches what it misses.
- Scam types: 7 (police, bank and relative impersonation, investment, health products, resort contracts, fake charity) + `other`, matching the KB scam doc; more can be added later (a migration widens the `CHECK`).
- Scam classification uses its own Gemini model (`GEMINI_SCAM_MODEL`, default `gemini-3.5-flash-lite`): the free tier's 20 requests/day per model then isn't shared with memory extraction, and the lite model answers in ~2 s, inside the in-call budget.
- In-call scam check budget 4 s (`SCAM_CHECK_TIMEOUT_SECONDS`) under Dograh's 5 s tool timeout: past it, or on any LLM error, the layer-1 result is the answer.
- Every caller gets the scam warning (no personal data needed), but only ACTIVE elders (consent given) get stored scam events and family alerts.
- Registration of a taken number returns 202 `link_requested`: tells the requester the number is registered (no personal data); accepted as inherent to the spec.
- Family sees call metadata + scam alerts only, never transcripts or memories; no per-call summaries: elder privacy; content stays for memory and scam analysis.
- Dograh-managed LLM/STT/TTS for calls (voice "Ngoc"), no Azure or Gemini provider: vi-VN works without extra provider keys; calls depend on Dograh's cloud service.
- Consent prompt says who registered the number and what the service does, not what family can see: keeps the consent turn short.
- Keep Clerk `createRouteMatcher` in `proxy.ts` (deprecated, removed in Clerk's next major): clean 307s before rendering, and the backend guards data anyway. Revisit on the Clerk major upgrade.

## Session notes

- Tooling: npm 11+ required — npm 10 fails to resolve `@hookform/resolvers` optional peers (`ERESOLVE`). uv ≥0.13 `uv init --app` creates a `src/` package layout; services use a flat `app/` instead (no build-system).

- Tests: backend `pytest` needs `docker compose up` (infra); the suite drops/recreates `ai_companion_test` (`TEST_DATABASE_URL`, must end in `_test`) and runs migrations on it.

- Auth: Clerk dev instance configured (setup steps in README); webhook endpoint URL must include the `/webhooks/clerk` path. svix 2.x `Webhook.verify()` returns `None`; parse the body separately.

- Frontend: Next 16.4 + Clerk Core 3, both newer than most docs/training data. Read `frontend/node_modules/next/dist/docs/` and `@clerk/nextjs` types before using an API. Clerk dev instances answer cookie-less HTML requests with a handshake redirect (`dev-browser-missing`); curl checks need a cookie jar + `-L` first. In Git Bash, exported env values starting with `/` get rewritten to Windows paths (`/sign-in` → `C:/Program Files/Git/sign-in`); use `.env.local` or PowerShell (or `MSYS_NO_PATHCONV=1` for CLI args).

- Signed-in checks without a browser: Clerk Backend API (`CLERK_SECRET_KEY`) `sessions.createSession({userId})` → `sessions.getToken(id)` → request the frontend with `Authorization: Bearer <jwt>` (`clerkMiddleware` accepts header tokens); revoke the session after. Users created in Clerk get role `family` in the DB until the webhook delivers `user.updated`, so admin tests need the webhook (ngrok) or a manual DB role update. Dev-only: a non-admin opening `/admin` logs "Could not validate `instant`" (the layout redirect stops the child page from rendering); harmless.

- Browser E2E (used in REG-01b): run a prod frontend build against the real backend + Clerk dev. Sign test users in via Clerk sign-in tokens in headless Chrome. Sync their names/emails by delivering signed Clerk webhooks locally (`user.created`/`user.updated` signed with `CLERK_WEBHOOK_SECRET` the way `svix_headers` in `backend/tests/conftest.py` does, POSTed to `/webhooks/clerk`). Delete the test users and their data afterwards.

- Dograh infra: `DOGRAH_JWT_SECRET` missing from `infra/.env` makes every `docker compose` command fail, even `up -d postgres`. The `dograh-api` image has no `curl`/`wget`; check from inside it with `python -c "import urllib.request ..."`. Docker Desktop forwards `host.docker.internal` to the host's loopback, so `fastapi dev` (127.0.0.1) is reachable; on Linux `host-gateway` is the bridge IP, so the backend must listen on `0.0.0.0` (firewall port 8000) — not yet tested on Linux. `Error connecting to cloudflared` warnings in `dograh-api` logs are expected: the upstream quick tunnel (public URL for telephony webhooks) is left out. Dograh still looks up `cloudflared` on every health check, and a slow failing DNS lookup (~4s) made the UI show "Backend connection failed". Compose maps `cloudflared` to 127.0.0.1 so it fails instantly. This machine also has an old standalone `dograh` compose project (containers `dograh-*` + `minio`, volumes `dograh_*`); unused, and its ports clash if started.

- Dograh: pre-call hook times out after 10s; web calls need hook mode `Always` + a `caller_number` context variable; greetings need a fallback for missing variables. The tool test panel sends preset values as typed (no `{{initial_context.*}}` rendering): paste a real `session_token` from the hook. Ending a text chat (`.../end`) needs body `{"expected_revision": n}`; without it the run never completes and no end-of-call webhook is sent.

- Dograh workflow: signing up on the self-host calls Dograh's cloud (managed service key, billing account, SIP), and the org default routes LLM/STT/TTS/embeddings through that managed connection. Any saved change, Context Variables included, creates a draft: publish it. Edge labels become LLM function names (non-ASCII → `_`), so use ASCII `snake_case` labels. Text chat speaks only the greeting, and the prompt's first turn waits for the caller. Gemini free tier is 20 requests/day per model.

- Dograh runs and tools: tool calls (name, LLM arguments, result, timestamps) are in `workflow_runs.logs -> realtime_feedback_events` (`rtf-function-call-start`/`-end`); text chats leave `logs.conversation` empty (query in `dograh/README.md`). Tools are loaded by UUID at run time, so tool edits need no workflow publish. Descriptions pasted from the JSON exports must drop the JSON escapes (`\"`).

- Scam eval: `scripts.eval_scam` caches classifier verdicts in `backend/.cache/scam_eval/<model>.jsonl` (gitignored), keyed by situation + `PROMPT_VERSION`; on a 429 it stops and the next run goes on. Use `--limit N` to keep some daily quota for live call tests. `--rules-only` needs no DB or key.

- Windows shells: Git Bash also rewrites `docker exec` container paths and API path arguments (`/app/...`, `/auth/me`); prefix with `MSYS_NO_PATHCONV=1`. Python on the Windows console needs `PYTHONIOENCODING=utf-8` to print Vietnamese.
