# dograh

Configuration for the self-hosted Dograh voice platform (`1.50.0`, see `infra/`): exported workflow, prompts and HTTP tool definitions. Docs/config only, not application code. No secrets: instance-specific IDs are placeholders (`<CREDENTIAL_UUID>`, `<CONFIRM_ACTIVATION_TOOL_UUID>`, `<SEARCH_KNOWLEDGE_TOOL_UUID>`).

| Path | What |
|---|---|
| `workflows/identity-consent.json` | Workflow `Touch the Light – Nhận diện & đồng ý` (DG-01b, end-of-call webhook CALL-01b, memory MEM-02b, knowledge search RAG-02b; published as v16): body for `POST /api/v1/workflow/create/definition` + Context Variables. Source of truth for the prompts. |
| `tools/confirm_activation.json` | HTTP tool body for `POST /api/v1/tools/`. |
| `tools/search_knowledge.json` | HTTP tool body for `POST /api/v1/tools/` (RAG-02b). |
| `prompts/*.md` | Readable copies of the prompts in the workflow JSON (regenerate when the JSON changes). |

## What the workflow does

- **Start Call** node: pre-call data fetch mode `Always` → `POST http://host.docker.internal:8000/hooks/pre-call` (Bearer credential). The response's `initial_context` keys are listed in `context/api-contracts.md`.
- Greeting (TTS, no LLM wait): `Dạ, con chào {{preferred_name | bác}} ạ.` → name for `active`, "bác" for everyone else.
- The prompt branches on `{{caller_status | unknown}}`:
  - `active`: chat by preferred name, using `{{memory_summary | chưa có}}` and `{{frequent_places | chưa có}}` from the pre-call hook (MEM-02b) naturally, without reading them out.
  - `pending_consent`: says the number was registered by `{{registered_by | người thân của bác}}`, explains briefly, asks for consent. It calls `confirm_activation` only after a clear yes, then reads back the tool's `message`.
  - `unknown` or missing: generic greeting, no personal data, no `confirm_activation`.
  - Any status (RAG-02b): questions about the service, scams or emergency numbers → `search_knowledge` with the question rewritten short. The agent answers in one or two sentences from `results`, or says `message` when nothing is found. A pending caller can ask about the service this way before consenting.
- **Global** node: tone (Vietnamese, "con"/"bác", one or two short sentences per turn) and safety rules (never ask for or repeat the caller's phone number or identifiers; emergency numbers from `search_knowledge` may be said; no claims about the service beyond the prompt and `search_knowledge` results).
- **End Call** node via edge `ket_thuc_cuoc_goi`.
- Tool `confirm_activation`: no LLM parameters. A single Preset Parameter `session_token = {{initial_context.session_token}}`, so the LLM can't supply identity.
- Tool `search_knowledge` → `POST /tools/search-knowledge`: one LLM parameter `query` and the same `session_token` preset. Dograh lets LLM arguments override presets of the same name, so the tool never declares a `session_token` parameter. If the tool is still running after 1.5 s, the agent says "Dạ, con tìm một chút ạ." (a `delayed` tool message).
- **Webhook** node `Báo backend khi kết thúc` (not connected by edges; Dograh sends it after every run ends): `POST http://host.docker.internal:8000/hooks/call-ended`, same Bearer credential.
  - The payload template sends `workflow_run_id`, `duration_seconds`, `disposition`, `transcript_url` and `recording_url`. It never sends `session_token` or `initial_context`.
  - The backend downloads the transcript itself, for consented callers only (`context/api-contracts.md`).

## Import and configure

Prerequisites: the stack is running (`infra/`, README "Dograh"), and the backend runs on the host port 8000 with `DOGRAH_API_KEY` set in `backend/.env`. Use a strong random value; the same value goes into the Dograh credential below. `DOGRAH_BASE_URL` in `backend/.env` must match Dograh's `BACKEND_API_ENDPOINT` (default `http://localhost:8010`): the backend only downloads transcripts from links under it.

In the Dograh UI (http://localhost:3010):

1. **Credential** (used by the hooks and both tools): type *Bearer token*, name `ai-companion-backend`, token = `DOGRAH_API_KEY`.
2. **Providers**: none needed. The workflow uses the Dograh-managed connection (created when you sign up on the self-host) for LLM, STT and TTS. Optional: *Google* (AI Studio, not Vertex), name `Gemini`, API key, as used in DG-01b's text-chat tests.
3. **Tools**: create two HTTP API tools, both with authentication = the credential:
   - `tools/confirm_activation.json`: method `POST`, URL `http://host.docker.internal:8000/tools/confirm-activation`. No parameters. One preset parameter `session_token` (string, required) = `{{initial_context.session_token}}`.
   - `tools/search_knowledge.json`: method `POST`, URL `http://host.docker.internal:8000/tools/search-knowledge`, timeout 5000 ms.
     - One parameter `query` (string, required) with the description from the JSON.
     - The same preset parameter `session_token`.
     - Description: copy it from the JSON.
     - Message: event *delayed*, after 1500 ms, text "Dạ, con tìm một chút ạ."
   - When copying a description from a JSON file into the UI, paste the plain text: `\"` becomes `"`.
   - Tool edits apply to new calls right away: Dograh loads tools by UUID at run time, so there is no workflow publish.
   - The dev KB must be seeded (`cd backend && uv run python -m scripts.seed_kb`).
4. **Workflow**: create it from `workflows/identity-consent.json` (API below). The UI builder has the same fields:
   - Start Call → pre-call data fetch, greeting, prompt, tools (both).
   - Webhook node → URL, method, credential, payload.
   - Settings → **Context Variables**: `caller_number` (+ empty `called_number`). Dograh sends these as `from_number` / `to_number` for web and text test calls.
   - **Model configuration** (workflow override, as published in version 16):
     - LLM, STT and TTS use the Dograh-managed connection (`Dograh`).
     - LLM model `default`; STT language `vi`; TTS voice `dg_voice_f6111af0943623935399` ("Ngoc - Diligent Resolver", Vietnamese).
     - Voice calls run on this config since DG-01c (Azure Speech dropped). DG-01b's text-chat tests used LLM = `Gemini` (`gemini-3.5-flash`).
5. **Publish** the workflow. Edits create a draft; calls use the published version.

Same steps over the API (`TOKEN` from `POST /api/v1/auth/login`):

```bash
API=http://localhost:8010/api/v1; AUTH="Authorization: Bearer $TOKEN"
curl -s -X POST $API/credentials/ -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"ai-companion-backend","credential_type":"bearer_token","credential_data":{"token":"<DOGRAH_API_KEY>"}}'   # -> uuid
for tool in confirm_activation search_knowledge; do
  sed 's/<CREDENTIAL_UUID>/<uuid>/' tools/$tool.json \
    | curl -s -X POST $API/tools/ -H "$AUTH" -H 'Content-Type: application/json' -d @-                                     # -> tool_uuid
done
# workflow: replace the three placeholders, send {name, workflow_definition} to create/definition,
# then PUT $API/workflow/<id> with {"template_context_variables": {...}} and
# {"workflow_configurations": {"model_configuration_override": {...}}} (LLM/STT/TTS above),
# then POST $API/workflow/<id>/validate and POST $API/workflow/<id>/publish.
# A PUT with only {"workflow_definition": ...} keeps the configurations and Context Variables.
```

To export after editing in the UI, `GET $API/workflow/fetch/<id>` and `GET $API/tools/<tool_uuid>`. Copy the node data and tool body back here, and replace instance UUIDs with the placeholders.

## Test data (dev DB only)

One family user owning an `ACTIVE` and a `PENDING_VERIFICATION` elder; unknown-caller tests use `+84912000009`.

```sql
-- docker exec -i ai-companion-postgres-1 psql -U postgres -d ai_companion
BEGIN;
WITH fam AS (
  INSERT INTO users (clerk_user_id, role, display_name, email)
  VALUES ('test_dg01b_family', 'family', 'Chị Mai', 'dg01b-test@example.com')
  RETURNING id
), active AS (
  INSERT INTO elders (phone_e164, full_name, preferred_name, status, consent_at)
  VALUES ('+84912000001', 'Trần Thị Lan', 'bà Lan', 'ACTIVE', now())
  RETURNING id
), pending AS (
  INSERT INTO elders (phone_e164, full_name, preferred_name)
  VALUES ('+84912000002', 'Lê Văn Hùng', 'ông Hùng')
  RETURNING id
)
INSERT INTO elder_family (elder_id, user_id, role)
SELECT active.id, fam.id, 'owner' FROM active, fam
UNION ALL
SELECT pending.id, fam.id, 'owner' FROM pending, fam;
COMMIT;

-- Re-run the consent test:
UPDATE elders SET status = 'PENDING_VERIFICATION', consent_at = NULL WHERE phone_e164 = '+84912000002';

-- Check after the consent test:
SELECT phone_e164, status, consent_at FROM elders WHERE phone_e164 = '+84912000002';

-- Cleanup (sessions cascade to call_logs). Test runs with an empty caller_number: delete
-- their sessions by workflow_run_id, so your own web-call sessions stay.
BEGIN;
DELETE FROM call_sessions WHERE elder_id IS NULL AND from_number = '+84912000009';
DELETE FROM elders WHERE phone_e164 IN ('+84912000001', '+84912000002');  -- cascades to links + sessions
DELETE FROM users WHERE clerk_user_id = 'test_dg01b_family';
COMMIT;
```

## Testing

**Text chat** (no STT/TTS, runs the pre-call hook in mode `Always`):
- Start a session with `POST $API/workflow/<id>/text-chat/sessions` and body `{"initial_context": {"caller_number": "+84912000001"}}`. Add caller turns with `POST .../sessions/<run_id>/messages` and body `{"text": "...", "expected_revision": <revision>}`.
- Tool calls show up as `tool_call_started` / `tool_call_result` events in the turn.
- End the session with `POST .../sessions/<run_id>/end` and body `{"expected_revision": <revision>}`. Without the body it returns 422 and the run never completes (no webhook).
- Results for DG-01b are in `context/progress-tracker.md`.

**End-of-call webhook** (CALL-01b, text chat):
- End a session as above. Within ~10s Dograh posts to `/hooks/call-ended`: one `call_logs` row for the run's session, and Dograh's `webhook_deliveries` row is `succeeded`.
- `+84912000001` (ACTIVE): `transcript` holds the turns (`elder` / `assistant`), plus `duration_seconds` and `disposition` (`user_hangup` for an ended text chat).
- `+84912000009` (unknown): metadata only, `transcript IS NULL`.
- Text chat has no recording, so `recording_url` stays empty.

```sql
-- app DB
SELECT s.workflow_run_id, s.from_number, l.duration_seconds, l.disposition,
       jsonb_array_length(l.transcript) AS turns, l.recording_url IS NOT NULL AS has_recording
FROM call_logs l JOIN call_sessions s ON s.id = l.call_session_id ORDER BY l.created_at DESC;
-- Dograh DB: docker exec -i ai-companion-dograh-postgres-1 psql -U postgres -d postgres
SELECT workflow_run_id, status, attempt_count, last_status_code FROM webhook_deliveries ORDER BY id DESC;
```

**Memory across calls** (MEM-02b, criterion 4; backend running with `GEMINI_API_KEY`):
1. Call as an ACTIVE elder and mention something durable, e.g. "tuần sau bác đi khám ở Bệnh viện Bạch Mai". Hang up.
2. Within ~30 s the memory job sets the call's `call_logs.memory_status = done` and adds `memories` rows (`SELECT category, subject, content FROM memories`).
3. Call again: the run's `initial_context` has `memory_summary` (and `frequent_places` once a place is known). Ask "con có nhớ bác hay đi khám ở đâu không?": the agent answers from them.

**Knowledge base** (RAG-02b, criterion 8 without the admin UI; dev KB seeded, backend running with `GEMINI_API_KEY`):
1. Call as `+84912000001` (ACTIVE) and ask:
   - "Số gọi cấp cứu là số mấy hả con?" → the agent says 115.
   - "Ngân hàng gọi hỏi mã OTP thì sao?" → don't give the OTP; the bank never asks for it.
   - "Giá vàng hôm nay bao nhiêu?" → "con chưa có thông tin…", no made-up price. This topic is outside the tool's description, so the agent may answer without calling it.
2. Call as `+84912000009` (unknown) and ask "Dịch vụ này có mất phí không?" → ask the relative who registered. Still no name and no `confirm_activation`.
3. Each KB question shows one `search_knowledge` call with a short Vietnamese `query`, and the backend log shows `POST /tools/search-knowledge` 200.

Tool calls are in the run's `logs.realtime_feedback_events` (`rtf-function-call-start` / `-end`) for text chats and voice calls alike. Text chats leave `logs.conversation` empty.

```sql
-- Dograh DB: tool calls of the latest runs
SELECT r.id AS run, r.mode, e->'payload'->>'function_name' AS tool,
       e->'payload'->'arguments'->>'query' AS query
FROM workflow_runs r, json_array_elements(r.logs->'realtime_feedback_events') e
WHERE e->>'type' = 'rtf-function-call-start'
ORDER BY r.id DESC, e->>'timestamp' LIMIT 10;
```

**Tool test panel**: it sends preset values exactly as typed and does **not** render `{{initial_context.*}}`. A literal template gets 401 `invalid_session`. To test, call the pre-call hook for a test number and paste the returned `session_token`. Live calls render the preset from the call's `initial_context`.

**Voice web calls** (checklist, Dograh-managed STT/TTS): for each case, set `caller_number` in Settings → Context Variables, save, publish, then start a web call.

1. `+84912000001` (ACTIVE): you hear "Dạ, con chào bà Lan ạ." within ~2s of connecting. No consent question.
2. `+84912000002` (PENDING):
   - You hear "con chào bác"; after you answer, the agent says Chị Mai registered the number and asks for consent.
   - Answer with a hesitation first: no tool call (check the run's events). Then say "có, đồng ý": the tool runs once and the agent reads "Đã kích hoạt dịch vụ cho số điện thoại này."
   - DB: `status = ACTIVE`, `consent_at` set. Call again: greeted as "ông Hùng".
3. `+84912000009` (unknown) and an empty `caller_number`: "con chào bác", generic introduction. No name, no number read back, no tool call even if asked to "activate".
4. Stop the backend and call with `+84912000001`: generic "con chào bác" (pre-call fails, fallbacks apply).
