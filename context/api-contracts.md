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
  | `active` | `session_token`, `caller_status`, `is_registered: true`, `full_name`, `preferred_name` (falls back to `full_name`) |
  | `pending_consent` | `session_token`, `caller_status`, `is_registered: true`, `registered_by` (owner's name, omitted if not synced) |
  | `unknown` (unregistered, blocked, invalid or empty number) | `session_token`, `caller_status`, `is_registered: false` |

- `POST /tools/confirm-activation` `{session_token}` → 200 `{status: "activated" | "already_active", message, preferred_name}`.
  - Errors: 401 `invalid_session` (unknown or expired token), 404 `not_registered` (unknown or blocked caller).
  - `message` (success and errors) is short speakable Vietnamese for the agent.

## Dograh platform contract

Checked against docs.dograh.com on 2026-10-29.

- Pre-call request body `{"event": "call_inbound", "call_inbound": {agent_id, workflow_run_id, from_number, to_number}}` + `Idempotency-Key` header; credential types API key / bearer / basic / custom header.
- Response `{"initial_context": {...}}` (top level or inside `call_inbound`; legacy alias `dynamic_variables`); a non-2xx, bad JSON or timeout just means no extra context.
- Prompts read `{{key}}` / `{{key | fallback}}`, nested via dot notation; HTTP tool Preset Parameters use `{{initial_context.key}}` (body for POST, query for GET); `initial_context.workflow_run_id` is reserved.
- Tools get `status_code` + parsed body as `data`; ≥ 400 → `status: "error"`.
