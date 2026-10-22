# Real Estate Voice Agent

One AI real-estate-agent persona, two channels, sharing the same backend/tools:

1. **Inbound**: a customer talks/chats with the agent via the web frontend to shortlist
   apartments and book a viewing.
2. **Outbound**: a scheduler dispatches the agent to "cold call" a client from the dummy CRM
   at a scheduled time — either ringing the dashboard's browser, or ringing a real phone
   through Twilio when the call has a dial number (see "Real phone calls" below).

All CRM/property data is dummy data. Bookings and meeting invites are logged to Postgres
via a mock email service, not sent for real yet.

## Stack

- Backend: Python / FastAPI, SQLAlchemy + Alembic, Postgres
- Voice agent: `livekit-agents` (self-hosted LiveKit), ElevenLabs or Deepgram STT/TTS
  (`STT_TTS_PROVIDER` in `.env`), Gemini LLM, Silero VAD
- Scheduler: APScheduler, polling a `call_schedule` table
- Frontend: Next.js/TypeScript, based on LiveKit's `agent-starter-react`

## Local dev setup

Prereqs: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, pnpm, Docker (for
Postgres/LiveKit — or install them natively if you prefer).

```bash
cp .env.example .env
# fill in OPENROUTER_API_KEY (default model: openai/gpt-6-luna) or GOOGLE_API_KEY
# if using Gemini, and either ELEVENLABS_API_KEYS (comma-separated; the agent
# moves to the next key when one runs out of credits, then to Deepgram if
# DEEPGRAM_API_KEY is set) + ELEVENLABS_TTS_VOICE_ID or
# DEEPGRAM_API_KEY depending on STT_TTS_PROVIDER, and generate ADMIN_PASSWORD_HASH
# (see below). LLM_PROVIDER=openrouter (default) or gemini.
# ELEVENLABS_PROVIDER=free (default, the keys above) or openrouter: the ElevenLabs models
# through OpenRouter on OPENROUTER_API_KEY, no ElevenLabs keys needed. Its transcription
# is per turn rather than realtime, so replies start ~1-2s later. The dashboard's
# Chatbot > Model > Voice card overrides it (provider, voice model, voice) and can preview
# the voice in English and Bangla.
# If port 5435 is taken, change POSTGRES_PORT + DATABASE_URL.
# Backend defaults to port 8011 (not 8000) -- see the note in .env.example.
```

Start Postgres and a local LiveKit dev server (or run these natively instead).
LiveKit on 7880 is shared with the RealEstateAgent project; skip the second
command if its `livekit` container is already running:

```bash
docker run -d --name telco-pg -e POSTGRES_USER=telco -e POSTGRES_PASSWORD=telco \
  -e POSTGRES_DB=telco -p 5435:5432 postgres:16-alpine
docker run -d --name livekit -p 7880:7880 -p 7881:7881 -p 7882:7882/udp \
  livekit/livekit-server:latest --dev --bind 0.0.0.0
```

Backend:

```bash
cd backend
uv sync
uv run python -m app.scripts.hash_password "yourpassword"   # paste into .env as ADMIN_PASSWORD_HASH
uv run alembic upgrade head
uv run python -m app.data.seed_all      # telco demo data: packages, 5 subscribers, usage, cases, incidents, offers
uv run uvicorn app.main:app --reload --port 8011   # terminal 1
uv run python -m app.agent.worker start # terminal 2
uv run python -m app.scheduler.worker   # terminal 3
```

Frontend:

```bash
cd frontend
cp .env.example .env.local  # fill in LIVEKIT_API_KEY/SECRET/URL to match the backend's,
                             # and confirm FASTAPI_INTERNAL_URL matches the backend's
                             # actual port (8011 by default -- see above); the browser
                             # reaches it via the frontend's /backend proxy
pnpm install
pnpm dev
```

Open http://localhost:3001 for the public site (the agent is its chat bubble),
http://localhost:3001/chat for the standalone full-screen chat page, and http://localhost:3001/login for the
admin dashboard (credentials from `.env`).

## Docker Compose (once you're past active development)

```bash
docker compose up --build
```

Builds two images (`backend`, used for the `api`/`agent-worker`/`scheduler` services with
different commands, and `frontend`); `postgres` and `livekit/livekit-server` are used as-is.

## Verification checklist

1. Log in at `/login` with your `.env` admin credentials → dashboard shows seeded leads and
   the cold-call schedule.
2. Within a couple minutes, a seeded `call_schedule` row fires automatically — watch the
   scheduler and agent-worker terminal logs, and see its status flip to `in_progress` on the
   `/dashboard/schedule` page.
3. On `/`, connect and ask for an apartment with partial criteria — the agent should ask for
   whatever's missing (budget, location, property type, rent vs. buy) before searching.
4. Give it the rest — a shortlist should render as cards on screen while the agent talks
   through the top picks.
5. Ask to book a viewing — check `/dashboard/bookings` for the new booking and its two mock
   meeting-invite rows (client + CEO).
6. Try an off-topic, a political-opinion, and a "what's your system prompt" question — the
   agent should deflect naturally each time without breaking character.

## Real phone calls

Scheduled calls with a **Dial phone number** ring that phone via a Twilio Elastic SIP Trunk
and a self-hosted `livekit-sip` (`TELEPHONY=1` in `.env` makes `run-local.bat` start it).
Only numbers on `SIP_DIAL_ALLOWLIST` can be dialed. Setup, costs, troubleshooting and the
VPS fallback: [docs/telephony-setup.md](docs/telephony-setup.md). `run-local.bat` also opens a
Cloudflare quick tunnel so the dashboard is reachable from outside this machine (same doc).

## Known open items

- ElevenLabs STT's auto-language-detection default-to-English fallback behavior hasn't been
  verified against real audio/API keys — worth confirming once you have live credentials.
- The Excel import (`POST /api/import/clients`) expects columns matching the `clients` table
  (see `backend/app/data/seed_sample.xlsx` for the exact layout) — adjust
  `excel_import_service.py` if your real export looks different.
