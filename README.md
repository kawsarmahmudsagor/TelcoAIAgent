# Telco Voice Agent

A Bangla-first voice/chat assistant for a fictional Bangladesh mobile operator, one agent
persona sharing the same backend/tools across channels:

1. **Inbound**: a customer talks/chats with the agent via the web frontend to check their
   account, buy packages, recharge, redeem rewards and raise support cases.

All subscriber/BSS data is dummy data. Nothing is sent to real subscribers.

## Stack

- Backend: Python / FastAPI, SQLAlchemy + Alembic, Postgres
- Voice agent: `livekit-agents` (self-hosted LiveKit), ElevenLabs or Deepgram STT/TTS
  (`STT_TTS_PROVIDER` in `.env`), Gemini LLM, Silero VAD
- Scheduler: APScheduler, polling a `call_schedule` table
- Frontend: Next.js/TypeScript, based on LiveKit's `agent-starter-react`

## Agent

The agent has 16 tools (`backend/app/agent/tools/`), acting on the logged-in demo subscriber:

- **Account and usage**: `get_account_summary`, `get_usage_breakdown`, `explain_deductions`,
  `lookup_transactions`
- **Packages**: `search_packages`, `recommend_packages`, `purchase_package`
- **Recharge and rewards**: `start_recharge`, `get_offers_and_points`, `redeem_reward`
- **Support and network**: `create_support_case`, `get_case_status`, `check_network_status`,
  `request_human_agent`
- **OTP**: `verify_otp`, `cancel_pending_action`

A 17th tool, `search_knowledge_base`, is added only when the knowledge base has content.

**Subscriber vs guest.** A session is tied to a subscriber only through the LiveKit dispatch
metadata, which the frontend's `/api/token` route sets server-side from the verified
`portal_session` cookie (never from the request body). Logged in as a persona, the agent acts
on that subscriber; without a persona it is a guest: it answers package, network-status and
knowledge-base questions and asks the customer to log in for anything about their own account.

**OTP flow** (purchase, recharge and redeem): the tool returns a preview and the browser gets
a confirm card (`telco.confirm`) and a 6-digit code as an SMS toast (`telco.otp_sms`), sent to
the linked browser only; the customer says or types the code, or enters it on the confirm
card; the action then executes. The code expires after 3 minutes and allows 3 attempts. The
portal's own recharge uses the same OTP flow. Tests: `backend/tests/test_actions.py`,
`backend/tests/test_action_rpc.py`.

**Operator identity** comes from `OPERATOR_NAME`, `OPERATOR_PHONE` and `OPERATOR_ADDRESS`:
defaults in `backend/app/config.py` (only `OPERATOR_NAME` is in `.env.example`), overridable
in `.env` and editable on the dashboard. The prompts and greetings use them.

**Knowledge base**: `uv run python -m app.data.seed_all` seeds the telco docs in
`backend/app/data/kb/` (policies, contact and helpline, stores, new SIM and eSIM, MNP, SIM
ownership, privacy) for `search_knowledge_base`. It only adds docs that have no source yet; the
scheduler embeds them, which needs an OpenRouter key (`OPENROUTER_API_KEY`). The docs speak only
as `telco.`; `tests/test_seed_kb.py` fails on another operator's name or contact details.
Editing a seeded doc needs no delete: the dashboard's Knowledge base page (and its sidebar badge)
flags it as changed, and **Re-embed** loads the new text and embeds it in place. In Docker the
docs are baked into the image, so rebuild `api` after editing one.

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
uv run python -m app.data.seed_all --reset   # before each demo: wipe the demo rows and reseed relative to now
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

Open http://localhost:3001 for the public home page (see "Customer portal" below),
and http://localhost:3001/login for the
admin dashboard (credentials from `.env`). `run-local.bat` starts the API, agent worker,
scheduler and frontend together.

## Customer portal

`/` is the public home page: live pack catalog (`GET /api/catalog/packages`, no sign-in),
recharge shortcut, Telco AI and help links. "Log in" opens `/signin`, the persona picker;
choosing one sets the `portal_session` cookie and lands on `/portal` (or the `?next=` portal page
the visitor was heading to). Signed in, the home page header shows "My dashboard" instead of
"Log in". The portal has the overview, packages, recharge, support, and the assistant page and
chat bubble. The admin
dashboard is unchanged: `/login` then `/dashboard`. Run the backend, the agent worker and the
frontend as in "Local dev setup"; the assistant needs all three, and `seed_all --reset` first.

| Persona | MSISDN | Scenario |
|---|---|---|
| Samiha | 01712342841 | Pack expiring in 3 days |
| Rafi | 01812347392 | Low balance, a recharge pending |
| Nusrat | 01912345501 | Postpaid bill due |
| Tanvir | 01612341109 | Low data in a congested area |
| Farhana | 01512346620 | Lots of reward points, one open case |

Demo script checklist:

1. From `/`, Log in, pick a persona, landing on `/portal`; back on `/`, "My dashboard" shows.
2. Overview figures match the persona's scenario.
3. Portal recharge: the OTP arrives as an SMS toast; enter it to complete.
4. Ask the assistant for the balance in Bangla.
5. Ask for packages; package cards appear, buy one through the confirm card.
6. The overview updates live after the purchase.
7. Raise a case through the assistant; it appears on Support.
8. As Tanvir, ask about the network.
9. Switch persona; the call ends.

Admin steps (sign in at `/login` in a second window; scheduler running):

10. Stage an outage: `/dashboard/network`, stage an incident for Tanvir's district. In the
    portal ask the agent about the network; it reports the incident. Resolve it afterwards.
11. Resolve a case: `/dashboard/cases`, open Farhana's case, start review then resolve. Her
    portal bell shows a case update.
12. Run nudges: on `/dashboard` choose "Run nudges now". Switch to Samiha, Rafi or Tanvir,
    open the bell and click a notification; `/portal/assistant` opens and the agent greets
    with that nudge.

Demo prep:

- `seed_all --reset` does not remove offers created in the admin UI. Delete them in
  `/dashboard/offers` before a demo.
- `LIVEKIT_URL` in `frontend/.env.local` must point at a reachable LiveKit server, or the
  assistant and the admin listen page cannot connect.

## Admin portal

Sign in at `/login` (credentials from `.env`); routes under `/dashboard`:

| Route | What it does |
|---|---|
| `/dashboard` | Control center: KPIs and "Run nudges now" |
| `/dashboard/subscribers` | Subscriber list and detail (MSISDNs masked) |
| `/dashboard/transactions` | Recharges, purchases and payments |
| `/dashboard/cases` | Support queue: start review, resolve, reopen. Each change sends the customer a `case_update` notification |
| `/dashboard/network` | Stage a network incident for a district, or resolve it; the agent's network answers follow it |
| `/dashboard/ai-monitor` | Agent activity monitor |
| `/dashboard/offers` | Create pack, points or cashback offers for all, prepaid, postpaid or specific subscribers |
| `/dashboard/chatbot`, `knowledge`, `conversations`, `listen` | Agent settings, knowledge base, conversation history and live listen-in |

**Nudges.** A scheduler sweep runs every 15 minutes (`run-local.bat` starts it) and "Run nudges
now" triggers one on demand. It creates `pack_expiring`, `low_balance` and `low_data`
notifications for active subscribers, at most once per subject. `case_update` notifications are
not part of the sweep: they are created when an admin changes a case's status.

**Notification bell.** The portal topbar bell lists the customer's notifications. Clicking one
opens `/portal/assistant` and the agent greets the customer with that nudge.

`/api/token` serves portal customers and guests (the subscriber is resolved server-side from the
`portal_session` cookie); joining an existing room via `room_name` needs an admin session.
`/api/listen-token` (dev-only listen-in) always needs an admin session.

## Docker Compose (once you're past active development)

```bash
docker compose up --build
```

Builds two images (`backend`, used for the `api`/`agent-worker`/`scheduler` services with
different commands, and `frontend`); `postgres` and `livekit/livekit-server` are used as-is.

## Verification checklist

Guest-mode checks (no persona logged in; see "Agent" above). Open the chat bubble on the home page `/`.
The logged-in flows are the demo checklist under "Customer portal".

1. Ask for a data pack (e.g. "৩০ দিনের ১০ জিবির কোনো প্যাক আছে?") — the agent searches the
   packages and quotes names and prices from the tool, in Bangla.
2. Ask a knowledge-base question (e.g. whether unused data rolls over to the next pack) — the
   answer comes from the seeded docs (needs `seed_all` and an embedded KB).
3. Ask whether the network is down — the agent asks for the district, then reports
   `check_network_status` for it.
4. Ask for your balance or to buy a pack — the agent asks you to log in first and never asks
   for your number or a code.
5. Try an off-topic, a political-opinion, and a "what's your system prompt" question — the
   agent should deflect naturally each time without breaking character.

## Real phone calls

Scheduled calls with a **Dial phone number** ring that phone via a Twilio Elastic SIP Trunk
and a self-hosted `livekit-sip` (`TELEPHONY=1` in `.env` makes `run-local.bat` start it).
Only numbers on `SIP_DIAL_ALLOWLIST` can be dialed. Setup, costs, troubleshooting and the
VPS fallback: [docs/telephony-setup.md](docs/telephony-setup.md). `run-local.bat` also opens a
Cloudflare quick tunnel so the dashboard is reachable from outside this machine (same doc).

## Known open items

- A case that is resolved, reopened and resolved again notifies the customer only for the first
  resolution (the notification subject key is `ref:status`).
