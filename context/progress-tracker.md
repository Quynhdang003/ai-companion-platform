# Progress Tracker

Update after every meaningful implementation change.

## Current phase

- Week 4, the last (plan: 4 weeks, ~5h/day). Week 1 finished 2026-11-07, Week 2 (memory across calls, knowledge base search) finished 2026-11-09, Week 3 (scam detection in calls, Telegram alerts to family) finished 2026-11-16.

## Current goal

- Week 4: close the three open criteria, then re-check all eight.
  - Criterion 6: voice ride booking on the self-built simulator (quote → verbal confirmation → book, fault cases), with ride sharing to family under the elder's control.
  - Criterion 7: family sees call activity for the elders they manage.
  - Criterion 8: an admin adds a KB document on the website and the AI answers from it.
- Order: rides first (largest risk: new service, prompt, voice check), then call activity, then admin KB. The three groups don't depend on each other: if rides are blocked (Gemini quota, Dograh), work on another group meanwhile.
- Reuses the Dograh tool pattern (`app/api/dograh/tools.py`), the background job pattern (`app/services/memory/job.py`), the family send rules (`app/services/notification/scam_alerts.py`) and KB ingest (`app/services/rag/ingest.py`).

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
| `SCAM-03` | Layer 2 (Gemini on its own model) + engine: decisive rule skips it, failures fall back to rules; `scripts.eval_scam` | 404 tests; live on 34/53 cases (`gemini-3.5-flash-lite`, free-tier quota): 31/34 high → high (rules alone 22/35), 34/34 warned with the right type; 3 transient errors fell back to rules; classifier p50 2.1 s, p90 3.8 s (in-call budget: see decisions) |
| `SCAM-04a` | `scam_events` (`391d115c2959`) + tool `POST /tools/check-scam`: templated warning for every caller, events for ACTIVE medium/high | 477 tests; dev backend + real Gemini: OTP → high by rule (0.02 s, alert `pending`), relative asking money → high by classifier (2.0 s), harmless → none (1.7 s, not stored), unknown caller warned, nothing stored |
| `NOTI-01a` | `NotificationChannel` + Telegram bot; `telegram_links` (`80d72daa5d7d`), one-time `/start` connect via `getUpdates` polling, connect/status/disconnect routes | 514 tests; Bot API mocked (httpx `MockTransport`, `FakeTelegramBot`); no real bot yet (user decision), see `NOTI-02b` |
| `NOTI-01b` | Dashboard Telegram card: connect by one-time link (waits for Start), status, disconnect | Lint + build; headless Chrome + Clerk dev vs a local fake Bot API: connected 2.9 s after `/start`, reused link rejected, disconnect, cancel; 1440/390 no overflow, no console errors |
| `NOTI-02` | Alert job: pending high scam events → Telegram to the elder's connected family (`240a783c442a`); retries, `failed`, `skipped` | 528 tests; real backend + dev DB vs a local fake Bot API: connect via `/start` 0.6 s, OTP check → alert 0.9 s later (name, type, level, time; no call words), blocked chat disconnected, no repeat alert, second type alerted |
| `SCAM-04b` | Dograh `check_scam` tool (8 s timeout) + prompt for every caller (workflow v20) | Text chat. ACTIVE: OTP, resort fee → high by rule (0.1–0.2 s); charity → medium, school fees look-alike → low (classifier 2.2–2.6 s, filler played); general question → `search_knowledge`; son's dinner → no call. Unknown: fake grandchild → high by classifier (2.4 s), nothing stored. `message` said word for word; no names, numbers or amounts in `situation`; agent never asked for the OTP; high events wait `pending` (no bot token yet, `NOTI-02b`) |
| `SCAM-03b` | Live eval of the full engine on all 53 cases (`gemini-3.5-flash-lite`, finished 2026-11-16) | 35/35 high → high with the right type, all 7 types + `other` (rules 22, classifier 13); medium 5/5 after `SCAM-03c` (4/5 before: `suspicious-03` flagged high); low and none 13/13 not warned (low: 2 low, 3 none; none: 8/8); classifier p50 2.1 s, p90 2.9 s, max 3.8 s, 0/31 over the 6 s budget; one transient 503 (`benign-04`) fell back to rules, re-ran fine |
| `SCAM-03c` | Engine caps a classifier `high` at `medium` when no signal from either layer is a request (`ASK_SIGNALS` in `engine.py`) | 532 tests (cap fires on a fake `high` verdict; a request named by either layer keeps `high`); rules find a request in all 13 classifier-decided high cases, so none can be capped; `suspicious-03` re-run live → medium (this time the classifier itself said medium: it is not stable on this case, the cap is); eval on 53 cases: nothing flagged high or warned beyond its label |
| `NOTI-02b` | Live check with the real Telegram bot: dashboard connect, then a scam case in text chat → alert on the family's Telegram. **Criterion 5 done** (with `SCAM-03b`: 35/35 high flagged across all 7 types + `other`) | 2026-11-16. Bot token valid, no webhook; connect from the dashboard by the owner of the ACTIVE elder. Text chat, workflow v21 (`caller_number` = the ACTIVE test number): money-sent-by-mistake story with a link → `check_scam` high / other by classifier, warning said, event alert `sent` 5.6 s after the check (Bot API accepted the message). Same session's v20 run as the unknown number: OTP → high / bank by rule, warned, nothing stored, no alert |
| `SIM-01` | Ride simulator core: quotes, bookings, seeded drivers, timestamp state machine, SQLite store | 66 tests (fake clock, fixed seed); real process at `TIME_SCALE=30`: quote → book → `COMPLETED` after 35 s, re-booking the quote 200, booking kept across a restart |
| `SIM-02` | Ride simulator maps (OSRM, Photon, built-in places, fallbacks) and four faults via `/sim/config` | 127 tests + 2 `live` (public OSRM and Photon) pass. Real process: OSRM quote Lang Ha → Bach Mai 4.1 km; built-in places < 0.1 s, Photon 4.3–4.7 s then 0 s cached; `no_driver` 409, `driver_cancels` cancelled 2 s after booking at `TIME_SCALE=30`, `timeout` 504 after 4 s, `price_surge` 72k → 130k; map servers unreachable → estimated quote, built-in places only |
| `RIDE-01` | `RideProvider` + simulator adapter, ride tables (`2743a0704e49`), tools `search_location`, `get_ride_quote`, `book_ride`, `last_ride` in the pre-call hook | 609 tests (77 new). Real backend (throwaway DB) + real ride-sim: built-in place 0.2 s, Photon address 2.5 s, OSRM quote 1.0 s; booking at once 409 `confirmation_required`, after 3.5 s booked, again the same ride; next call `last_ride` set (hook 10 ms) and both places found again from the earlier ride in 0.0 s; `price_surge`, `no_driver`, `timeout` (unavailable after 7 s), same place `too_short`, unknown option 404; pending and unknown callers 403 |
| `RIDE-02` | Tools `get_ride_status`, `cancel_ride`; ride sync job; cancel reason and sync time (`092895d242f7`) | 645 tests (36 new). Real backend (throwaway DB, sync every 3 s) + real ride-sim at x30: status read out from looking for a driver to arrived in 38 s; a ride nobody asked about stored `COMPLETED` by the job; `driver_cancels` → driver cancelled message 3 s after booking; cancel, cancel again, cancel on board refused; `timeout` → status and cancel unavailable in 7.1 s, also while the job hits the same timeout |
| `RIDE-03` | Ride sharing choice (`set_ride_sharing`, asked after the first booking), family ride updates on Telegram within it (`049aa92d4462`) | 667 tests (22 new). Real backend (throwaway DB, jobs on) + real ride-sim at x30 + a local fake Bot API: first booking asks; nothing sent for 5 s without an answer, `status` → booked sent 4 s later, then on board and arrived, no places; `details` → places and car + plate; `none` while on board → arrived skipped |
| `ACT-01a` | `GET /api/elders/{id}` (profile + activity counts) and `/calls` (time, duration, scam alerts, paged); linked family only | 680 tests (13 new): owner and viewer see it, strangers, pending requesters and unknown ids 404, admins 403; calls from the consent call on only; no transcript, recording or signal codes in the body |
| `ACT-01b` | `/dashboard/elders/[id]`: profile, activity tiles, paged call list with scam alert tags; elder cards link to it. **Criterion 7 done** | Lint + build. Prod build + backend (dev DB, no jobs) + Clerk dev, headless Chrome: owner opens the card, 24 visible calls (declined pre-consent call hidden), 20 + 4 over two pages, alert tags, no transcript text; pending elder explains why empty; another family user and a malformed id get the not-found card; no overflow at 1440/390, no console errors. Test users and data removed |
| `KB-01a` | Admin KB routes `/api/admin/kb/documents` (list with accent-free title search, read, add, edit, delete), embedded on save; `update_document` split out of `sync_document` (a new source alone no longer re-embeds) | 703 tests (23 new): family 403, signed out 401; a saved document answers `search_knowledge` at once, an edit replaces its chunks, a delete removes them; taken title 409 before embedding, also when saved meanwhile (savepoint); embedding errors 503 / no key 500 store nothing and keep the old version |
| `KB-01b` | `/admin` KB page: table with accent-free title search, add/edit dialogs, delete confirm; shadcn `table`, `dialog`, `textarea`, `alert-dialog`; Toaster in the admin layout. Criterion 8 on the web side done; the agent's answer in a text chat is the user's step | Lint + build. Prod build + backend (dev DB, jobs off, real Gemini) + Clerk dev, headless Chrome, 21 checks: empty form and taken title refused in the form; the "Số tổng đài chính thức" document added (indexed in 0.9 s), edited (1.0 s), found by "tong DAI"; a scratch document deleted after a cancelled confirm; no overflow at 1440/390 (dialog fits); family user sent from `/admin` to the dashboard, its token 403 on the admin API. `search_knowledge` with real embeddings: Viettel Post, Vina and Vietcombank questions → the new document first (0.3–1.0 s), ambulance → emergency numbers, gold price → nothing. Test users removed; the hotlines document stays in the dev DB |

## In progress

- None.

## Next

In this order (about 5 h left). Each unit gets its own detailed plan when it starts; units of one group may run back to back in a session (`ai-workflow-rules.md`, "Working sessions").

Branches, stacked: `feat/ride-booking` (holds the Week 4 plan) ← `feat/act-01-call-activity` (criterion 7, done) ← `feat/kb-01-admin-kb`. Merge them in that order, or rebase each onto `main` with the plan commit.

Rides (criterion 6), branch `feat/ride-booking`:

- `RIDE-04` (Dograh): the six ride tools + prompt (verbal confirmation before `book_ride`, `cancel_ride` and sharing changes). Text chat, then voice → criterion 6.
  - Tool timeouts above the backend's 7 s provider wait (`search_location` can take ~6 s on public Photon for an address the simulator doesn't know), with a `delayed` filler, like `check_scam`.
  - Prompt: "same as last time" → search the names in `last_ride`; read every quote; call `book_ride` with the type the caller agreed to, only after a clear yes; on 409 `confirmation_required`, ask and wait.
  - Sharing: when `ask_sharing`, the question is in `message`; a plain yes → `status`, `details` only when the elder asks for places or the car, no → `none`. "Đừng báo nữa" or a change in any call → `set_ride_sharing` after confirming.

Admin KB (criterion 8), branch `feat/kb-01-admin-kb` (stacked on `feat/act-01-call-activity`):

- Text chat (the user, Dograh): ask "số tổng đài Viettel Post là số mấy" → the agent reads 1900 8095 from "Số tổng đài chính thức" (in the dev DB since `KB-01b`) → criterion 8 done.

Closing:

- `CHK-02`: re-check all 8 criteria, prune session notes, update the README.

## Backlog (unscheduled)

- `SCAM-05`: post-call scan of stored transcripts, a safety net for scams the agent didn't check in the call; alerts only if that call has no alert of the same type yet.
- Admin scam patterns page: add and edit patterns per scam type (reuses `sync_patterns` in `app/services/scam/patterns.py`; same shape as the admin KB page).
- Deploy: Vercel (frontend) + VPS Docker Compose, with self-hosted OSRM and Photon in `infra/docker-compose.yml` (ride-sim only needs their URLs).
- Web call simulation page; point `/demo` "Mở trang gọi thử" at it.
- Public "Tầm nhìn" / "Tài nguyên" pages (waiting for design).

## Open questions

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
- Ride simulator map data from public servers, behind `Router` and `Geocoder` interfaces (user decision, 2026-11-16): the OSRM demo server and public Photon, no setup or API key. Fallbacks keep a demo independent of them: straight-line distance × a factor when OSRM fails, a built-in list of Hanoi places when Photon fails. Only addresses are sent out, never names or phone numbers. Self-hosting both at deploy is a URL change.
- Place search answers well-known places from the simulator's built-in list (41 places from OpenStreetMap) without asking Photon, and asks Photon only for anything else, with a 6 s timeout and an in-memory cache: public Photon took 3–6 s from here on 2026-11-16 (even its `/status`), so it only serves addresses the list doesn't have. A more precise request ("phố Bạch Mai" instead of "Bạch Mai") reaches Photon.
- Ride sharing with family is the elder's choice (user decision, 2026-11-16): `none`, `status` (booked, on the way, arrived, cancelled + time) or `details` (plus pickup, destination and plate number). Asked once on the first booking and stored with its time; changed or withdrawn by voice in any call, effective at once, also for a ride in progress. Not asked yet = nothing shared. No live vehicle location.
- Ride updates for family are queued for every ride and read the elder's choice when sent: a change or a withdrawal applies at once without touching the queue. An update queued before the elder answered the sharing question waits for the answer (15 min at most), so the first ride's "booked" still goes out once they say yes. The driver accepting or arriving isn't sent: four messages per ride at most.
- Family call activity starts at the call in which the elder consented (user decision, 2026-11-16): a caller who never agreed shows nothing, and calls before agreeing (declined ones included) stay hidden after consent too. The consent call is found as the elder's latest call started before `consent_at`, so no column records it.
- `book_ride` takes the ride type the caller agreed to (the plan said no LLM parameter): when several types were quoted and read out, "the latest quote" alone could book the wrong one. A ride type is no identifier, so invariant 1 holds.
- Ride tools answer every outcome the caller should hear with a 200, a `status` and a speakable message, and keep HTTP errors for the agent's own mistakes (unknown option number, booking too soon): the agent reads `message` either way.
- Rides leave now, no scheduled pickups: those need timed dispatch in the simulator. Ride tools are for ACTIVE elders only; family sees no rides on the dashboard, only the Telegram messages the elder allowed.
- Hybrid search in PostgreSQL: no extra infra, tolerant to STT errors.
- KB search thresholds stay as they are (open question closed in `KB-01b`): "số tổng đài Viettel Post" returned the emergency-numbers document only because the KB had no hotlines document. With one added on the admin page, hotline questions rank it first with real embeddings; the other documents still follow in the top 3, and the agent reads the first. A question about reporting scams ranks the service intro first and the hotlines (156) second.
- Admin KB saves embed within the request (documents are short, ≤ 20 000 characters, one embedding request, ~1 s): the document is searchable when the page says it is saved, and a failed embedding stores nothing.
- KB search open to every live call, unknown and pending-consent callers included: the KB holds no personal data, and callers can ask about the service before consenting.
- Embeddings: `gemini-embedding-001` at 768 dims for memories and KB: smaller HNSW index, enough for short Vietnamese text. Changing it means a full re-index.
- Telegram for urgent alerts, Email for reports: email too slow for scam alerts.
- Telegram connect by a one-time deep link (`t.me/<bot>?start=<token>`) read with `getUpdates` polling: no webhook, so no public URL or tunnel is needed; the token is hashed, expires in 15 min and works once. One chat per family account; two accounts may share a chat.
- Family scam alerts reach each member at most once: one successful send marks the event `sent`, and members whose send failed then aren't retried (a retry would duplicate it for the others). All sends failing → retried 30 s apart, `failed` after 5. Nobody connected, or the event is over 1 h old → `skipped`: no late alerts (user decision).
- Scam check split: real-time in-call + async post-call memory extraction.
- In-call scam check is a tool the agent calls (`check_scam`), not a per-turn check: Dograh 1.50.0 has no per-turn backend hook (node types: `startCall`, `agentNode`, `endCall`, `globalNode`, `webhook`, `trigger`, `qa`). The agent calls it when the caller tells it about a suspicious call or request; the post-call scan (`SCAM-05`) catches what it misses.
- Scam types: 7 (police, bank and relative impersonation, investment, health products, resort contracts, fake charity) + `other`, matching the KB scam doc; more can be added later (a migration widens the `CHECK`).
- Scam classification uses its own Gemini model (`GEMINI_SCAM_MODEL`, default `gemini-3.5-flash-lite`): the free tier's 20 requests/day per model then isn't shared with memory extraction, and the lite model answers in ~2 s, inside the in-call budget.
- In-call scam check budget 6 s (`SCAM_CHECK_TIMEOUT_SECONDS`), under the `check_scam` tool's 8 s timeout in Dograh (HTTP tools have no upper limit; the default 5 s was too tight: a first call in a fresh process took 4 s and fell back). Past it, or on any LLM error, the layer-1 result is the answer; a delayed tool message covers the wait.
- A classifier `high` with nothing asked for is capped at `medium` in the engine (user decision, 2026-11-16): high alerts the family, so it needs a request signal (money, code, personal data, link/app) from the rules or the classifier. Chosen over a prompt change: the classifier flips between medium and high on such stories (`suspicious-03`), and the cached eval verdicts stay valid. A real scam whose request neither layer names is warned as medium and not alerted.
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

- Browser E2E (used in REG-01b): run a prod frontend build against the real backend + Clerk dev. Sign test users in via Clerk sign-in tokens in headless Chrome. Sync their names/emails by delivering signed Clerk webhooks locally (`user.created`/`user.updated` signed with `CLERK_WEBHOOK_SECRET` the way `svix_headers` in `backend/tests/conftest.py` does, POSTed to `/webhooks/clerk`). Delete the test users and their data afterwards. Admin users: create the Clerk user with `public_metadata.role = admin` and insert the DB row with role `admin` (no webhook needed).
  - Next to a running dev frontend: build with `NEXT_PUBLIC_API_BASE_URL` set to the test backend (inlined at build time; `next build` and `next dev` keep separate output, so the dev server is untouched), start it on another port with `node node_modules/next/dist/bin/next start -p 3001` (PowerShell's Start-Process can't run `npx`), and add that origin to the test backend's `CLERK_AUTHORIZED_PARTIES` (the JWT `azp`). Rebuild without the override afterwards. Headless Chrome is driven over the DevTools protocol with the backend venv's `websockets`.

- Dograh infra: `DOGRAH_JWT_SECRET` missing from `infra/.env` makes every `docker compose` command fail, even `up -d postgres`. The `dograh-api` image has no `curl`/`wget`; check from inside it with `python -c "import urllib.request ..."`. Docker Desktop forwards `host.docker.internal` to the host's loopback, so `fastapi dev` (127.0.0.1) is reachable; on Linux `host-gateway` is the bridge IP, so the backend must listen on `0.0.0.0` (firewall port 8000) — not yet tested on Linux. `Error connecting to cloudflared` warnings in `dograh-api` logs are expected: the upstream quick tunnel (public URL for telephony webhooks) is left out. Dograh still looks up `cloudflared` on every health check, and a slow failing DNS lookup (~4s) made the UI show "Backend connection failed". Compose maps `cloudflared` to 127.0.0.1 so it fails instantly. This machine also has an old standalone `dograh` compose project (containers `dograh-*` + `minio`, volumes `dograh_*`); unused, and its ports clash if started.

- Dograh: pre-call hook times out after 10s; web calls need hook mode `Always` + a `caller_number` context variable; greetings need a fallback for missing variables. The tool test panel sends preset values as typed (no `{{initial_context.*}}` rendering): paste a real `session_token` from the hook. Ending a text chat (`.../end`) needs body `{"expected_revision": n}`; without it the run never completes and no end-of-call webhook is sent.

- Dograh workflow: signing up on the self-host calls Dograh's cloud (managed service key, billing account, SIP), and the org default routes LLM/STT/TTS/embeddings through that managed connection. Any saved change, Context Variables included, creates a draft: publish it. Edge labels become LLM function names (non-ASCII → `_`), so use ASCII `snake_case` labels. Text chat speaks only the greeting, and the prompt's first turn waits for the caller. Gemini free tier is 20 requests/day per model.

- Dograh runs and tools: tool calls (name, LLM arguments, result, timestamps) are in `workflow_runs.logs -> realtime_feedback_events` (`rtf-function-call-start`/`-end`); text chats leave `logs.conversation` empty (query in `dograh/README.md`). Tools are loaded by UUID at run time, so tool edits need no workflow publish. Descriptions pasted from the JSON exports must drop the JSON escapes (`\"`).

- Scam eval: `scripts.eval_scam` caches classifier verdicts in `backend/.cache/scam_eval/<model>.jsonl` (gitignored), keyed by situation + `PROMPT_VERSION`. The free tier also has a per-minute limit (12 back-to-back calls hit it): calls start 6 s apart, a 429 is retried once after 65 s, and a second 429 (daily quota) stops the run; the next run goes on. The daily quota resets at midnight Pacific time (15:00 in Vietnam, 14:00 during US daylight saving time). Use `--limit N` to keep some daily quota for live call tests. `--rules-only` needs no DB or key. The cache holds the engine's result, not the raw classifier verdict: after a change to how the engine treats a verdict, drop the affected rows from the cache file so they re-run.

- Smoke runs with a second backend process: its scheduler works on every row of its database, so against the dev DB it handles the user's own pending work (a NOTI-02 smoke marked a real pending alert `skipped`; restored). Point such runs at a throwaway database, or turn the jobs off. `TELEGRAM_API_BASE_URL` points the bot at a local fake Bot API for end-to-end checks without a real bot.

- Windows shells: Git Bash also rewrites `docker exec` container paths and API path arguments (`/app/...`, `/auth/me`); prefix with `MSYS_NO_PATHCONV=1`. Python on the Windows console needs `PYTHONIOENCODING=utf-8` (or `-X utf8`) to print Vietnamese. curl in Git Bash sends Vietnamese query strings in the wrong encoding (`--data-urlencode "q=chợ Hôm"` finds nothing): send them from Python or PowerShell, or percent-encode the UTF-8 by hand.
