# API Contracts

Read before adding, changing or calling any backend route. Behavior only; implementation lives in `backend/app/`.

## Conventions

- Success returns the resource or result body. Errors return `{"error": {"code", "message"}}` with the HTTP status (`app/core/errors.py`). Invalid body or parameters → 422 `validation_error`; other framework errors → `http_error`.
- Auth dependencies:
  - `CurrentUser` (`app/core/auth.py`): Clerk session JWT as `Authorization: Bearer`; missing/invalid → 401 `unauthorized`. A verified user missing from the DB is created as `family`.
  - `require_role(*roles)` (`app/core/auth.py`): wrong role → 403 `forbidden`. `FamilyUser` = `require_role(family)`.
  - `require_dograh_key` (`app/core/dograh_auth.py`): `Authorization: Bearer <DOGRAH_API_KEY>`; missing/wrong → 401 `unauthorized`.
- Required env unset → 500 `*_not_configured`: `auth_not_configured` (`CLERK_ISSUER`), `webhook_not_configured` (`CLERK_WEBHOOK_SECRET`), `dograh_not_configured` (`DOGRAH_API_KEY`).
- Phone input is normalized with `normalize_vn_phone` (VN mobile + landline); responses carry E.164.
- CORS: browser origins from `CORS_ORIGINS`.

## Web API (Clerk JWT)

F = family-only (`FamilyUser`); others accept any role (`CurrentUser`).

| Route | | Success | Errors |
|---|---|---|---|
| `GET /api/me` | | 200 `{id, clerk_user_id, role}` | |
| `POST /api/elders` `{full_name, phone, preferred_name?}` | F | 201 `{result: "created", elder}`; 202 `{result: "link_requested"}` (number taken: request sent to the owner, no elder data; repeat while pending is a no-op) | 409 `already_linked`, 422 `invalid_phone` |
| `GET /api/elders` | F | 200 `[{id, full_name, preferred_name, phone_e164, status, my_role, created_at}]` | |
| `GET /api/link-requests/incoming` | F | 200 pending requests on elders I own: `[{id, elder: {id, full_name}, requester: {display_name, email}, created_at}]` | |
| `GET /api/link-requests/outgoing` | F | 200 requests I sent: `[{id, phone_e164, status, elder_full_name (approved only), created_at, decided_at}]` | |
| `POST /api/link-requests/{id}/approve` | F | 200 `{id, status, decided_at}`; requester becomes `viewer` | 404 `not_found` (missing or not owner), 409 `already_decided` |
| `POST /api/link-requests/{id}/reject` | F | 200 `{id, status, decided_at}` | 404 `not_found` (missing or not owner), 409 `already_decided` |

## Clerk webhook

- `POST /webhooks/clerk`: Svix-verified (`CLERK_WEBHOOK_SECRET`) → 200 `{received: true}`.
  - `user.created` / `user.updated`: upsert user; role from `publicMetadata.role` (missing/unknown → `family`), `display_name`, primary `email`.
  - `user.deleted`: removes the user, their family links and link requests (elders stay).
  - Other event types ignored.
  - Errors: 400 `invalid_signature`, 400 `invalid_payload`.

## Dograh-facing (Bearer `DOGRAH_API_KEY`)

- `POST /hooks/pre-call` `{"event": "call_inbound", "call_inbound": {workflow_run_id, from_number, …}}` → 200 `{"initial_context": {...}}`. Unset keys are omitted.

  | `caller_status` | Keys |
  |---|---|
  | `active` | `session_token`, `caller_status`, `is_registered: true`, `full_name`, `preferred_name` (falls back to `full_name`), `memory_summary`, `frequent_places` |
  | `pending_consent` | `session_token`, `caller_status`, `is_registered: true`, `registered_by` (owner's name, omitted if not synced) |
  | `unknown` (unregistered, blocked, invalid or empty number) | `session_token`, `caller_status`, `is_registered: false` |

  - `memory_summary`: up to 8 of the elder's non-place memories (most important, then most recent) as whole sentences, ≤ 600 characters.
  - `frequent_places`: up to 5 place memories, most mentioned first, as `subject: content` joined by `; `.
  - Both are omitted while the elder has no such memories. No LLM call in the hook.

- `POST /tools/confirm-activation` `{session_token}` → 200 `{status: "activated" | "already_active", message, preferred_name}`.
  - Errors: 401 `invalid_session` (unknown or expired token), 404 `not_registered` (unknown or blocked caller).
  - `message` (success and errors) is short speakable Vietnamese for the agent.

- `POST /tools/search-knowledge` `{session_token, query}` → 200 `{found, message, results: [{title, content}]}`.
  - `query` (1–500 chars) is the caller's question, written by the LLM; never logged or stored.
  - Any caller with a live session (active, pending consent, unknown or blocked): the KB holds no personal data.
  - Up to 3 KB chunks (≤ 800 chars each) from the hybrid search, best first. If the query embedding fails or takes over 2 s, the search is lexical only.
  - Nothing relevant → 200 with `found: false`, `results: []`. `message` is speakable Vietnamese: "Dạ, con chưa có thông tin về việc này ạ." (not found) or "Dạ, con tìm được thông tin rồi ạ." (found; the agent answers from `results`).
  - Errors: 401 `invalid_session`, 422 `validation_error` (missing or empty `query`).

- `POST /hooks/call-ended` `{workflow_run_id, duration_seconds?, disposition?, transcript_url?, recording_url?}` → 200 `{received: true}`. Dograh's end-of-call Webhook node; values are strings, `""` = not sent, `duration_seconds` is rounded to whole seconds.
  - Upserts one `call_logs` row for the run's `call_session` (Dograh retries deliveries).
  - A run without a call session (its pre-call hook never reached us) is ignored: 200, nothing stored.
  - Transcript and `recording_url` are stored only if the session's elder is `ACTIVE` at that point (includes consent given during the call). Others get metadata only, and the transcript isn't downloaded.
  - A stored transcript queues memory extraction (`memory_status = pending`); a background job does it later, outside the request. A retried delivery doesn't re-queue a log whose extraction is queued, done or failed.
  - The backend downloads the transcript from `transcript_url`, which must start with `DOGRAH_BASE_URL`.
  - Errors:
    - 401 `unauthorized`.
    - 422 `validation_error`.
    - 422 `invalid_transcript_url` (outside `DOGRAH_BASE_URL`).
    - 503 `transcript_unavailable` (download failed or not a Dograh transcript): nothing stored, Dograh retries.

## Dograh platform contract

Checked against docs.dograh.com on 2026-10-29. Verified against the Dograh `1.50.0` source and live text-chat runs on 2026-11-03 (DG-01b); where the docs differ, the verified behavior is written here.

- Pre-call request body `{"event": "call_inbound", "call_inbound": {agent_id, workflow_run_id, from_number, to_number}}` + `Idempotency-Key: dograh-pre-call-<run id>` header; credential types API key / bearer / basic / custom header.
  - `agent_id` and `workflow_run_id` are integers.
  - Web and text-chat calls take `from_number` / `to_number` from the `caller_number` / `called_number` context variables, and send `""` when they are unset.
  - Text-chat sessions also run the hook, but only in mode `Always`, and once per session.
  - Timeout 10s. An unreachable backend fails fast, and the call starts without the context.
- Response `{"initial_context": {...}}` (top level or inside `call_inbound`; legacy alias `dynamic_variables`); a non-2xx, bad JSON or timeout just means no extra context.
  - The keys are merged flat into the run's `initial_context`, which Dograh stores with the run, `session_token` included.
  - Reserved keys are dropped: `workflow_run_id`, `call_id`, `provider`, `runtime_configuration`, `model_overrides`, `model_configuration_snapshot`, `model_configuration_overrides`.
  - `greeting_override` replaces the Start Call greeting (unused).
- Prompts and greetings read `{{key}}` / `{{key | fallback}}` (legacy `{{key | fallback:text}}`), nested via dot notation. A missing key without fallback renders as an empty string (the docs say the raw placeholder is spoken).
- HTTP tool Preset Parameters use `{{initial_context.key}}` (body for POST, query for GET); `initial_context.workflow_run_id` is reserved.
  - Use the `initial_context.` prefix: a bare `{{key}}` can be shadowed by LLM-gathered variables.
  - The tool test panel sends preset values as typed, without rendering templates.
- HTTP tool body (POST, no `body_template`): LLM parameters and resolved presets as one flat JSON object. LLM arguments override presets of the same name, so a tool never declares an LLM parameter named like a preset (verified in the `dograh-api 1.50.0` source, `custom_tool.py`, 2026-11-09).
- Tool `messages`: `start` text is spoken when the tool starts; a `delayed` text (`after_ms`) is spoken only while the tool is still running at that time (`tool_messages.py`).
- Tools get `status_code` + parsed body as `data`; ≥ 400 → `status: "error"`. Default tool timeout 5000 ms.
- End-of-call **Webhook node** (verified in the `dograh-v1.50.0` source, 2026-11-06):
  - **Node:** `type: "webhook"`, not connected by edges. Fields: `endpoint_url`, `http_method`, `credential_uuid` (same auth header as the pre-call hook), `custom_headers`, `payload_template`.
  - **When:** sent by the `process_workflow_completion` worker after the run ends. Voice calls and text chats upload the transcript first, so `transcript_url` is set when there was any message. A text chat ends with `POST /workflow/{id}/text-chat/sessions/{run_id}/end` `{expected_revision}` (or inactivity).
  - **Payload:** a template rendered with the same renderer as prompts. Every placeholder becomes a string (missing → `""`).
    - Variables: `workflow_run_id`, `call_time` (run created), `cost_info.call_duration_seconds`, `gathered_context.*` (incl. `call_disposition`), `initial_context.*`, `recording_url`, `transcript_url`.
    - The transcript text itself isn't available.
  - **Links:** `{BACKEND_API_ENDPOINT}/api/v1/public/download/workflow/{token}/{transcript|recording}`, with no auth (the token is the capability). They redirect 302 to a MinIO URL signed for 1h, on `MINIO_PUBLIC_ENDPOINT` (fallback `http://localhost:9000`).
  - **Transcript file:** UTF-8 text, one line per final message: `[<ISO time>] user: …` / `[<ISO time>] assistant: …`. Multi-line messages continue unprefixed; no tool or system lines.
  - **Delivery:**
    - Headers `X-Dograh-Delivery-Id`, `X-Dograh-Workflow-Run-Id`, `X-Dograh-Delivery-Attempt`; no signature.
    - Timeout 30s, up to 5 attempts with backoff 30s → 60s → 120s → 240s.
    - Retried on 408/425/429/500/502/503/504 and network errors; any other non-2xx is dead-lettered at once.
