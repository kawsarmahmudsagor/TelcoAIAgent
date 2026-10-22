# Real phone calls via Twilio (Elastic SIP Trunk + self-hosted livekit-sip)

## Context
Scheduled cold calls today only "ring" the dashboard's browser incoming-call screen
(`scheduler/jobs.py` creates room `coldcall-{id}` + dispatches the agent; agent waits for a
browser participant). Goal: when the admin gives a scheduled call a **dial number** (one of
their own/team phones — demo only), the agent calls that real phone through Twilio. Calls
without a dial number keep the existing browser flow untouched. The carrier leg is
swappable: Twilio now; a local Bangladeshi SIP trunk / Asterisk PBX (as in the company's
Frontdesk project) later only changes the outbound trunk's address and credentials. Setup
runs on the user's Windows machine (Docker Desktop) now and moves unchanged to a VPS later.
All work happens on branch `feat/twilio-calling`.

## Decisions (agreed)
- Per-call routing via new optional `call_schedule.dial_number` (E.164), set at creation
  only (immutable afterwards). Never auto-dial `clients.phone` (seed data has real-looking
  +880 numbers).
- `SIP_DIAL_ALLOWLIST` in `.env` (entries normalized with the same E.164 function; empty
  allowlist = reject all). Checked at schedule time (400) and again before dialing.
- Voicemail/AMD: out of scope (demo, user answers own phone).
- No Twilio SDK. Installed `livekit-api` 1.2.0 / `livekit-agents` 1.7.0 already provide
  `sip.create_sip_participant`, `sip.create_outbound_trunk`, `SipCallError`, and
  `livekit.agents.beta.tools.end_call.EndCallTool`. New dep: `phonenumbers` (`uv add`).

## Key risk: the PC is not publicly reachable → Phase 0 spike first
The PC sits behind the office NAT/firewall, and Docker Desktop adds a second NAT layer
(Windows → Docker VM → container). Twilio must send RTP audio (UDP) to livekit-sip's public
IP; this often fails behind corporate NAT (symptom: call connects, no/one-way audio). So **before app code**, prove the media path with one manual call. If it
fails, run the same telephony compose override on a small cloud VM (only livekit + redis +
livekit-sip) and point `LIVEKIT_URL` at it — no code changes.

### Phase 0 — Accounts + connectivity spike (user actions; I write files + docs)
0. Network check: compare router WAN IP with `curl https://api.ipify.org` (CGNAT if they
   differ). Not a blocker for outbound-only: try the manual call first even behind NAT
   (symmetric RTP may get through); one-way/no audio → move LiveKit+SIP+Redis to a ~$5 VPS.
   Restrict any opened 5060/RTP ports to Twilio's IP ranges (SIP scanners).
1. Twilio (chosen provider; Telnyx considered, swappable later): account (**upgrade** before E2E — trial prepends a message and needs a keypress),
   buy voice number, **Voice Geo Permissions → Bangladesh**, Elastic SIP Trunk with
   Termination URI (`<name>.pstn.twilio.com`) + Credential List, assign number.
2. Windows only, no WSL distro: Docker Desktop runs `redis` + `livekit-sip` containers next to
   the existing `livekit` container, with published ports (`5060/udp`, `5060/tcp`,
   `10000-10100/udp`) instead of host networking. Windows Firewall inbound rules for those
   ports. Fallbacks if audio fails: Docker Desktop host networking (Settings → Resources →
   Network), then the VPS. WSL distro setup dropped.
3. Start telephony stack (step 1 below), run `create_sip_trunk.py`, then
   `lk sip participant create` to your phone. Pass = two-way audio.

## Implementation

### 1. Infra — opt-in files, local `--dev` flow untouched
- Leave `docker-compose.yml` and README local `--dev` setup as is.
- Windows local: `run-local.bat` with `TELEPHONY=1` starts livekit with `--redis-host`,
  plus `redis` and `livekit-sip` containers on a shared Docker network (sip reaches
  `livekit:7880` / `redis:6379` by name; published 5060 + 10000-10100/udp). Without
  `TELEPHONY=1`, behavior is unchanged.
- New **`docker-compose.telephony.yml`** (self-contained, same three services) for a Linux
  host/VPS, where `livekit-sip` may use `network_mode: host`.
- New **`docker-compose.telephony.vm.yml`** (merge override with the base file on the
  full-stack VM): livekit `--config /etc/livekit.yaml`, mounts `./livekit.yaml`,
  `LIVEKIT_KEYS: "${LIVEKIT_API_KEY}: ${LIVEKIT_API_SECRET}"` (≥32-char secret), publishes
  `50000-50100/udp`; adds redis + livekit-sip.
- Shared shapes (Linux/VPS files; on Windows the bat uses service names instead of
  127.0.0.1): `redis` (redis:7-alpine, published `127.0.0.1:6379:6379` only);
  `livekit-sip` (`network_mode: host`, config via `SIP_CONFIG_BODY` with `${VAR}`
  substitution: api key/secret, `ws_url: ws://127.0.0.1:7880`, `redis.address:
  127.0.0.1:6379`, `sip_port: 5060`, `rtp_port: 10000-10100`, `use_external_ip: true`) — no
  secrets committed.
- Pin a known-good `livekit/livekit-server` + `livekit/sip` pair (recorded after M0), not `latest`.
- `livekit.yaml` (VM): add `redis` block (`redis:6379`, the compose service name).
- New `backend/app/scripts/create_sip_trunk.py`: `lk.sip.list_outbound_trunk` → reuse by name,
  else `lk.sip.create_outbound_trunk(CreateSIPOutboundTrunkRequest(trunk=SIPOutboundTrunkInfo(
  name, address, numbers=[TWILIO_PHONE_NUMBER], auth_username, auth_password)))`; prints id.
- VM hardening notes in docs: restrict 5060/RTP to Twilio signalling/media IP ranges.

### 2. Config — `backend/app/config.py`, `.env.example`
`sip_outbound_trunk_id`, `sip_dial_allowlist` (+ property → normalized set),
`sip_ring_timeout_s: int` (default 25, below typical carrier voicemail pickup),
`sip_max_call_duration_s: int` (default 600, cost cap), `twilio_phone_number`,
`twilio_sip_termination_uri`, `twilio_sip_username`, `twilio_sip_password`.

### 3. Data — model, migration, schemas, API
- `models/call_schedule.py`: `dial_number: Mapped[str | None] = String(20)`.
- Alembic migration (down_revision `b4d8f2a61c37`) adding the column.
- New `backend/app/services/phone_numbers.py`: `normalize_e164(raw)` (phonenumbers, default
  region BD, `is_valid_number`, raises ValueError) and `is_dial_allowed(e164, settings)`.
- `schemas/call_schedule.py`: `CallScheduleCreate.dial_number: str | None = None`;
  `CallScheduleOut.dial_number`. (Not on `CallScheduleUpdate` — immutable.)
- `routes_schedule.py::create_schedule_entry`: if dial_number → normalize, allowlist, and
  trunk-id-configured checks, each `HTTPException(400, "<plain message>")`.
  Blank/whitespace dial_number → `None` (browser call).
  `get_incoming_call` / `decline_call`: 409 for entries with `dial_number` (phone calls have
  no browser ringing screen).
  New `POST /api/schedule/{id}/hangup`: for `dispatched`/`in_progress` entries → transition
  to `cancelled` "ended from dashboard" + `delete_room`. `delete_schedule_entry` also calls
  `delete_room` first if the entry is still live (stops a ringing/live phone call).
- `call_schedule_repo.create(..., dial_number=None)`.

### 4. Scheduler — `scheduler/jobs.py::_dispatch_call`
Add `"dial_number": entry.dial_number` to dispatch metadata. Nothing else changes.

### 5. Agent
- `entrypoint.py`: replace `_ringing_call_schedule_id` with a parser returning
  `(call_schedule_id, dial_number)`; unit-tested. Non-phone path stays exactly as today.
- **Phone path order** (after `ctx.connect()`):
  1. `session_context.resolve(...)`; if `userdata.client is None` → failed "lead not found",
     `await ctx.delete_room()`, shutdown (never ring a phone with the inbound persona).
  2. Build STT/TTS/LLM, VAD, `Agent` (tools incl. per-session `EndCallTool`), `AgentSession`
     — all before dialing so the callee doesn't hear dead air after picking up.
  3. `ok = await phone_dial.dial(...)`; on False → return (dial already cleaned up).
  4. `session.start(agent, room=ctx.room, room_options=room_io.RoomOptions(
     participant_identity=f"phone-{id}", delete_room_on_close=True))` (not the deprecated
     `RoomInputOptions`; `delete_room_on_close` prevents a silent open line on agent errors).
  5. Short greeting via `generate_reply(..., allow_interruptions=False)` so the callee's
     "Hello?" doesn't cut it off.
- New `backend/app/agent/phone_dial.py`:
  - `async def dial(ctx, call_schedule_id, number, settings) -> bool`: load the entry; abort
    unless it exists, status ∈ {dispatched, in_progress}, `dial_number == number`, and the
    number passes the allowlist. Then `ctx.api.sip.create_sip_participant(
    CreateSIPParticipantRequest(room_name=ctx.room.name, sip_trunk_id, sip_call_to=number,
    participant_identity=f"phone-{id}", wait_until_answered=True,
    ringing_timeout=Duration(seconds=settings.sip_ring_timeout_s),
    max_call_duration=Duration(seconds=settings.sip_max_call_duration_s)))` — no outer
    `wait_for` (library sizes the HTTP timeout). `livekit.api.SipCallError` →
    `classify_sip_failure(e.sip_status_code)`, logging `e.metadata`; any other exception →
    failed "telephony error: …". On failure: `transition(from {dispatched,in_progress})`,
    `await ctx.delete_room()`, `ctx.shutdown(reason=...)`, return False.
  - Then answered `transition`; if it returns False (cancelled meanwhile) → delete room,
    shutdown, return False.
  - Pure `classify_sip_failure(code: int | None)`: 486→missed "busy"; 603→cancelled
    "declined"; 408/480/487→missed "no answer"; 403→failed "rejected by carrier (check Geo
    Permissions/credentials)"; None/other→failed "telephony error: <code>". Confirm against
    real `e.metadata` from M0 busy/reject/ring-out calls and adjust.
- Hang-up detection: sync `ctx.room.on("participant_disconnected")` handler for `phone-{id}`
  → `ctx.shutdown()` (log disconnect reason), so callee hang-up promptly runs the existing
  `_mark_call_schedule_completed` callback. Session closed with `CloseReason.ERROR` → record
  failed "agent error" instead of completed.
- `userdata.py`: `is_phone_call: bool = False` (default keeps `test_schedule_followup` working);
  `session_context.resolve` sets it from metadata.
- `EndCallTool(delete_room=True, end_instructions=None)` from
  `livekit.agents.beta.tools.end_call`, constructed **per phone session** via a small
  `_session_tools(userdata)` helper in the entrypoint. Browser cold calls unchanged.
- `persona.py` (phone only): no screen — describe apartments verbally, short turns; say a
  brief goodbye then call end_call (including after `confirm_interest` / `schedule_followup`);
  for bookings confirm the email on file (put `client.email` in the prompt) rather than asking
  the caller to spell one.
- `tools/search_apartments.py`: when `is_phone_call`, skip the `send_text` shortlist and
  return a verbal-summary instruction instead of "shown on the customer's screen".
- `tools/schedule_followup.py`: load the current entry first, pass
  `dial_number=entry.dial_number` to `create`.

### 6. Frontend
- `lib/api-client.ts`: `dial_number` on schedule types; `createSchedule` takes an options
  object `{client_id, scheduled_at, dial_number?}`; error display uses the API's `detail`.
- `app/dashboard/schedule/page.tsx`: optional "Dial phone number" input (omitted when blank);
  phone badge + number in list; "Hang up" button for live phone entries.
- `components/app/scheduled-call-watcher.tsx`: skip entries with `dial_number`.

### 7. Docs
- `docs/telephony-setup.md`: Twilio account steps (below), Windows/Docker Desktop setup
  (Phase 0), trunk script, spike command, VPS migration + hardening, troubleshooting (no audio = RTP/NAT; 403 = Geo
  Permissions/credentials; voicemail picks up = lower ring timeout/disable voicemail).
- README: replace "Future: real telephony" with a pointer; recommend switching STT/TTS to
  Deepgram in **Dashboard → Voice models** (runtime setting, not the env var).

### 8. Cloudflare quick tunnel for the frontend (run-local.bat)
Goal: dashboard reachable from outside the PC whenever the app starts. Not needed for the
phone call itself (SIP trunks use no webhooks).
- `run-local.bat`: after launching services, if `cloudflared` is on PATH, open a
  "Tunnel" window running `cloudflared tunnel --url http://localhost:3000` (free quick
  tunnel, no account/domain; random `https://*.trycloudflare.com` URL printed in that
  window, new each run). If missing, print `winget install Cloudflare.cloudflared` and
  continue. `SKIP_TUNNEL=1` disables it. Optional `CLOUDFLARE_TUNNEL_TOKEN` → run a named
  tunnel instead (stable hostname, later, needs a domain).
- Only one hostname is tunneled, so the browser must reach FastAPI through Next.js:
  `next.config.ts` adds `rewrites()` `/backend/:path*` → `${FASTAPI_INTERNAL_URL ??
  'http://localhost:8010'}/:path*`; `lib/api-client.ts` defaults `FASTAPI_URL` to `/backend`
  (same-origin, no CORS). Existing `NEXT_PUBLIC_FASTAPI_URL` still overrides; document
  clearing it in `frontend/.env.local` to use the proxy.
- `next.config.ts` `allowedDevOrigins` += `'*.trycloudflare.com'`.
- Limitation (documented): over the tunnel, dashboard pages + scheduling phone calls work;
  browser voice/chat (customer widget, browser-mode cold calls, listen-in) does **not**,
  because LiveKit's `serverUrl` is local and WebRTC media can't go through the tunnel. Those
  keep working on the local machine.
- Security: the dashboard becomes public → `.env` must have a strong admin password hash and
  non-default `JWT_SECRET`; run-local.bat warns if `JWT_SECRET` is the default.
- Verify: run-local.bat → open the printed trycloudflare URL on a phone (mobile data) →
  log in → leads/schedule load → schedule a phone call → it rings.

## Accounts, costs, env
- Numbers: buy **one** Twilio number (caller ID). The test phone is the user's own mobile
  (in `SIP_DIAL_ALLOWLIST`; on trial also a Twilio Verified Caller ID).
- Paid: Twilio prepaid credit (~$20 upgrade; covers number monthly fee + per-minute to BD
  mobile). Usage-only, keys already held: OpenRouter (or Gemini free tier), Deepgram /
  ElevenLabs. Free: LiveKit, livekit-sip, Postgres, Redis, Cloudflare quick tunnel, Silero.
  Optional: VPS (only if audio fails), domain (only for a named tunnel).
- Twilio setup: sign up (verify email + BD mobile) → 2FA → upgrade with an
  international-enabled card → buy US voice number → Voice Geo Permissions: Bangladesh →
  Elastic SIP Trunk (Termination URI + Credential List, attach number).
- New `.env`: `SIP_OUTBOUND_TRUNK_ID`, `SIP_DIAL_ALLOWLIST`, `SIP_RING_TIMEOUT_S`,
  `SIP_MAX_CALL_DURATION_S`, `TWILIO_PHONE_NUMBER`, `TWILIO_SIP_TERMINATION_URI`,
  `TWILIO_SIP_USERNAME`, `TWILIO_SIP_PASSWORD` (Twilio vars used only by the trunk
  script). Optional: `TELEPHONY=1`, `SKIP_TUNNEL=1`, `CLOUDFLARE_TUNNEL_TOKEN`. Frontend:
  clear `NEXT_PUBLIC_FASTAPI_URL`, optional `FASTAPI_INTERNAL_URL`. Strong `JWT_SECRET` /
  admin password once tunneled; strong LiveKit keys on a VPS.
- Blockers to check early: office NAT/firewall (audio), IT policy on cloudflared + SIP ports,
  Twilio trial limits, BD caller-ID delivery, voicemail on test phone.

## Milestones (each independently testable)
M−1 branch setup: commit the current uncommitted incoming-call work on `feature/openrouter`
(the plan builds on its `answered_at`/missed-status migrations), then
`git checkout -b feat/twilio-calling` from there. **All plan changes go to
`feat/twilio-calling` only** ·
M0 Phase 0 spike (manual call; runs **in parallel** with M1–M4 — only M5 depends on it) ·
M1 data/API + tests · M2 scheduler metadata + agent dial with fake `ctx.api` tests ·
M3 persona/tools/end_call · M4 frontend · M5 E2E.

## Verification
- `uv run alembic upgrade head` (Postgres 5433) **before** `uv run pytest` (tests hit the real DB).
- New tests: `test_phone_numbers.py` (`+880-1711-234567`, `01711234567`, invalid, allowlist
  normalization, empty allowlist); route 400s (off-allowlist, invalid, trunk unset) and 409
  for incoming/decline on phone entries (pattern: `test_schedule_decline.py`);
  `CallScheduleOut` includes `dial_number`; metadata parser; `test_phone_dial.py`
  (`classify_sip_failure` table incl. None/403/487; `dial()` with fake `ctx.api` raising
  `SipCallError` → DB status/outcome + delete_room; off-allowlist never calls the API);
  `schedule_followup` carries `dial_number`; persona/search_apartments phone text;
  `dial()` aborts without calling the API when the entry is cancelled/deleted/mismatched;
  hangup route + DELETE-on-live entry call `delete_room`; `_dispatch_call` puts
  `dial_number` in metadata (fake `LiveKitAPI`); `_session_tools` adds EndCallTool only for
  phone. DB-touching tests get a cleanup fixture like `test_schedule_decline.py`; fake
  `ctx.delete_room` returns an awaitable.
- E2E (after M0, Twilio upgraded, **voicemail disabled on the test phone**): schedule with your
  number → rings with Twilio caller ID → greeting by name → converse → agent says goodbye and
  hangs up → `completed`. Reject → `cancelled`; ring out → `missed`; hang up mid-call →
  `completed` within seconds. No dial number → browser flow unchanged.

