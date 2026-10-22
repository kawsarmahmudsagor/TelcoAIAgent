# Remove Twilio / phone calling

## Context
Client: number calling out of scope. Remove all Twilio/SIP telephony code, config, docs, tests, frontend UI. Keep browser LiveKit voice flow: incoming/decline routes, scheduler dispatch, `outbound_coldcall`/`inbound_chat` channels, `missed` status, browser cold-call ring timeout, `speech_numbers.py`, `client_phone` lead capture, Cloudflare tunnel feature (`run-local.bat` tunnel, `frontend/next.config.ts` `/backend` rewrite, `FASTAPI_INTERNAL_URL`).

## Step 0: Branch
`git checkout -b fix/twilio-removal` from current `feat/elevenlabs-multiApiKeys` (default; 9 commits ahead of master, so the PR includes them unless they merge first). Alternative: base on master. Re-check `git status` first (reviewers saw clean tree; session-start snapshot showed uncommitted voice changes); stage by path so unrelated changes stay out of removal commits. Confirm base with user.

## Commit order (each leaves tests green)

### 1. Agent runtime
- `entrypoint.py`: browser cold-call path uses `phone_dial.parse_ringing_call` (:468) and `record_call_end` (:495, :510). Move two helpers into `entrypoint.py` first: `_ringing_call_schedule_id(metadata) -> UUID | None` and `_record_call_end(id, status, outcome)`. Keep the browser ring-timeout/missed block (:486-498). Remove only the `ringing.dial_number` branch (:468-471), `_run_phone_call` (:386-462), `EndCallTool` in `_session_tools` (+ docstring :307-310), `_END_CALL_DESCRIPTION`, `allow_interruptions=` in `_greet` and its "Hello?" comment. Drop now-unused imports (`rtc`, `room_io`, `CloseEvent`, `CloseReason`, `EndCallTool`, `phone_dial`).
- Drop `is_phone_call`: `userdata.py` (+comment), `session_context.py`, `transcript.py`, `repositories/conversation_repo.py`, `schemas/conversation.py`, `models/conversation.py` (field + :33 docstring). Safe before DB drop (server default).
- `persona.py`: `_PHONE_CALL_NOTE`, `_phone_email_instruction`, `_END_REASONS_OUTBOUND/_INBOUND`, `{end_reasons}`; simplify dead `cold_call` local.
- `tools/search_apartments.py`: remove both phone branches (:198-232); always shortlist + web summary.
- `tools/book_appointment.py:31` docstring "(on a phone call ...)".
- Delete `app/agent/phone_dial.py`, `tests/test_phone_dial.py`. New `tests/test_entrypoint.py` with moved `test_parse_browser_call_metadata_has_no_number`, `test_parse_non_coldcall_metadata` retargeted at new helper; optional test `_session_tools` has no end-call tool.
- `test_prompts.py`: drop `_phone` variants, `test_phone_end_reasons_match_the_channel`, end_call assertion (:42). `test_transcript.py` :203-218.

### 2. Schedule dial_number + SIP infra code
- `routes_schedule.py`: `_validated_dial_number`, `_reject_phone_call` + calls, `/hangup` route (phone-only; only caller is schedule page button), unused `get_settings` import, comments :179-180, hangup docstring.
- `schemas/call_schedule.py`, `repositories/call_schedule_repo.py`, `models/call_schedule.py:35`, `scheduler/jobs.py:28-30`, `tools/schedule_followup.py:33-38` (drop comment/dial copy, keep `entry` lookup).
- `config.py:96-113`: all `sip_*`, `twilio_*`.
- Delete `services/phone_numbers.py`, `scripts/create_sip_trunk.py`, `tests/test_phone_numbers.py`, `tests/test_schedule_phone.py`. First move `test_delete_live_call_tears_room_down` and `test_delete_pending_call_leaves_rooms_alone` into `test_schedule_decline.py` (reuse `deleted_rooms` fixture; `_entry` without `dial_number`).
- `pyproject.toml`: drop `phonenumbers` (only importer was `phone_numbers.py`); `uv lock`.

### 3. Alembic migration (after 1-2)
New revision, `down_revision='c8e4f1a7d203'`. Upgrade: cancel pending `call_schedule` rows with `dial_number IS NOT NULL` (outcome "phone calling removed") so they don't ring a browser; drop `call_schedule.dial_number`, `conversations.is_phone_call`. Downgrade: re-add `dial_number` `sa.String(20)` nullable, `is_phone_call` Boolean `server_default='false'`. Don't edit old migrations. Keep `missed` enum migration.

### 4. Frontend (verify: `pnpm exec tsc --noEmit && pnpm lint`)
- `lib/types/schedule.ts`, `lib/types/conversation.ts`: remove fields.
- `lib/api-client.ts`: remove `hangUp`/`hangUpCall`; fix comments :179, :181.
- `app/dashboard/schedule/page.tsx`: `dialNumber` state + submit spread (:79), phone input, "Rings on" column (head :203, cell :234-240), Hang up button + `hangingUpId`/`hangUpCall`, `PhoneOffIcon` import, `LIVE_STATUSES` if unused, page description :128, re-fit form grid :134.
- `scheduled-call-watcher.tsx:54`: drop `dial_number` skip.
- `conversations-view.tsx` `ChannelLabel` (also used by `conversation-detail-view.tsx:258`): fix `Pick<..., 'channel'|'is_phone_call'>`, `PhoneIcon`; `overview-view.tsx:9,165`.
- Leave `incoming/[id]/page.tsx`, `client_phone`, `agent-disconnect-button` alone.

### 5. Infra + docs
- Delete `docker-compose.telephony.yml`, `docker-compose.telephony.vm.yml`, `twilio.txt`, `TWILIO_CALLING_PLAN.md`, `docs/telephony-setup.md` — first move its tunnel section (:126-143) and non-SIP "Moving LiveKit to a VPS" (:145) into `README.md`.
- `livekit.yaml`: keep, remove redis block (:7-10); tell user it's now unreferenced.
- `.env.example` :118-137: remove SIP/TWILIO/`TELEPHONY`; keep `SKIP_TUNNEL`, `CLOUDFLARE_TUNNEL_TOKEN` (reword comment).
- `run-local.bat`: remove :12-13, :28; collapse if/else :43-52 to else branch (no telephony stop); collapse :127-132.
- `README.md` :8-9, :105-110.
- `PROMPTS_AND_GUARDRAILS.md`: :17, :123, §4 (:168-195), :214, :221, :258, §6.6 (:308-311), :337-338, :389/:401/:456, changelog/token tables; renumber. Keep generic phone-digit TTS lines (:549, :561).
- `QUESTIONNAIRE.md`: :4, :31, :50, :307, Part 4 (:334-354), :392, :420; renumber Part 5.
- Tell user: leftover `SIP_*`/`TWILIO_*` in their untracked `.env` are ignored (`extra="ignore"`), can delete.

## Verification
- `grep -ri "twilio\|sip_\|dial_number\|is_phone_call\|phonenumbers\|telephony"` clean, excluding old migrations `c5e19a7d3f42`, `f3c7a2d9e514`, new migration, and `uv.lock`.
- `cd backend && uv run pytest` (real DB on port 5433) after each commit; `uv run alembic upgrade head` then `downgrade -1` then `upgrade head`.
- Frontend tsc + lint via pnpm.
- Run app: schedule browser call; incoming, decline, ring-timeout missed all work.

## Pass 2 amendments (apply to steps above)
- Step 1: moved helpers also need `import json` and `_LIVE_STATUSES` ({dispatched, in_progress}); `_mark_call_schedule_answered` bool return now unused (drop it). `persona.py` `cold_call` local (:124-126) deleted outright. `test_prompts.py`: also drop `prompts["inbound_phone"]` use in `test_screen_is_only_mentioned_for_web_chat` (:56). `test_transcript.py` :203-218: edit only (remove `is_phone_call=True` and its assert), keep cold-call channel test.
- Step 2: `models/call_schedule.py` remove comment+field :33-35. `/hangup` backend is not phone-gated (UI only); removal still fine. Delete with `test_schedule_phone.py`: `test_hangup_*`, `test_phone_call_has_no_browser_incoming_screen`, `test_list_includes_dial_number`. Rewrite lost `test_dispatch_metadata_carries_dial_number` as a scheduler test asserting `call_schedule_id`, `channel`, status `in_progress`, no `dial_number` key.
- Step 3: cancel rows with `dial_number IS NOT NULL` in status pending, dispatched, in_progress → `'cancelled'`, `completed_at=now()`. Warn: upgrade touches real rows in dev DB; run `alembic upgrade head` before pytest (conftest does not create schema).
- Step 4 extra: `frontend/app/home/page.tsx:99-101` "Take a phone call" card + :216-217 copy (+ `PhoneCallIcon` if unused); `schedule/page.tsx` also remove `handleHangUp` (:109-121), `LIVE_STATUSES` + comment :32-33, phone input ~:160-170; `scheduled-call-watcher.tsx` comment :53; `overview-view.tsx` drop `PhoneIcon` only, keep `PhoneOutgoingIcon`; `frontend/DESIGN.md:11` reword.
- Step 5: VPS section can't move as-is (references deleted compose files, SIP/Redis) — drop it, or rewrite as one `docker run livekit/livekit-server` recipe using `livekit.yaml`. Tunnel section: change "scheduling phone calls" to "scheduling calls". Before deleting compose files run (or tell user to run) `docker compose -f docker-compose.telephony.yml down`, since `run-local.bat` loses its only stop command for telephony LiveKit (port 7880). `.env.example` range :118-136. `PROMPTS_AND_GUARDRAILS.md` extra: :195, :471, :473, :475, :499, :503, :524, :526, :537. `twilio.txt` is in git history since e05afbc: if it holds credentials, tell user to rotate in Twilio console.
- Verification grep: exclude `node_modules`, `.mypy_cache`, `__pycache__`; also grep `hangUp|hangup|PhoneCallIcon|phone call` in `frontend/app` and `frontend/components`.

## Review log
- Pass 1: found browser cold-call path depends on phone_dial helpers (keep/move), browser tests hiding in phone test files, livekit.yaml should be kept, tunnel docs live in telephony-setup.md, many missed frontend/doc refs, migration should cancel pending dial rows, commit ordering. All applied.
- Pass 2: verified line refs; found missing imports for moved helpers, extra test breakages (`test_prompts` :56, lost dispatch test), home-page marketing copy, VPS doc section unmovable, migration should cover live rows, docker stop gap, twilio.txt credential rotation, base-branch choice. All applied as amendments.
