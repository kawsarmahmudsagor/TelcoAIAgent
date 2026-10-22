# Real phone calls (Twilio)

A scheduled cold call can ring a real phone instead of the dashboard's browser
incoming-call screen. Give the call a **Dial phone number** when scheduling it;
leave it blank and the call works exactly as before (browser).

```
Your phone ◄─PSTN─► Twilio ◄─SIP/RTP─► livekit-sip ◄─► livekit-server ◄─► agent worker
(+8801…)        (Elastic SIP Trunk)  (Docker)          (Docker)            (native)
```

The phone joins the call's LiveKit room as one more participant, so the agent,
tools and persona are the same as for a browser call. Only numbers on
`SIP_DIAL_ALLOWLIST` can ever be dialed.

## 1. Twilio account (one-time)

1. Sign up at <https://www.twilio.com/try-twilio>; verify your email and your own
   mobile (on a trial account that makes it a Verified Caller ID, the only kind of
   number a trial can call).
2. Turn on two-factor auth (User settings).
3. **Upgrade** (Admin → Billing): add a card and prepay credit (about $20). Trial
   accounts play a "trial account" message and need a keypress on every call.
   Many Bangladeshi cards block international online payments; use an
   international/dual-currency card or enable it with your bank.
4. **Buy one number** (Phone Numbers → Buy a number): US, Voice capability. It's
   the caller ID. Your test phone is your own mobile; you don't buy that.
5. **Allow Bangladesh** (Voice → Settings → Geo Permissions → tick Bangladesh).
6. **Elastic SIP Trunk** (Explore Products → Elastic SIP Trunking → Create trunk):
   - Termination: set a URI, e.g. `realestate.pstn.twilio.com`, and add a
     Credential List (a username and strong password you choose).
   - Numbers: attach the number from step 4.

## 2. `.env`

```ini
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX                 # step 4, E.164
TWILIO_SIP_TERMINATION_URI=realestate.pstn.twilio.com
TWILIO_SIP_USERNAME=...                          # Credential List
TWILIO_SIP_PASSWORD=...
SIP_DIAL_ALLOWLIST=+8801XXXXXXXXX                # your own phone(s), comma-separated
SIP_OUTBOUND_TRUNK_ID=                           # filled in at step 4 below
TELEPHONY=1
```

`SIP_RING_TIMEOUT_S` (default 25) and `SIP_MAX_CALL_DURATION_S` (default 600, a
cost cap) are optional. Keep the ring timeout below your carrier's voicemail
pickup, or turn voicemail off on the test phone: there's no answering-machine
detection, so voicemail counts as "answered".

Also switch STT/TTS to **Deepgram** in Dashboard → Voice models; it handles 8 kHz
phone audio well. (That's a runtime setting; `STT_TTS_PROVIDER` only seeds it.)

## 3. Windows: Docker Desktop + firewall

No WSL setup needed. `run-local.bat` with `TELEPHONY=1` stops its plain `livekit`
container and starts `docker-compose.telephony.yml` instead: LiveKit (with
Redis), Redis and livekit-sip. The backend, agent and frontend keep running
natively against `ws://127.0.0.1:7880`.

Allow the SIP ports through Windows Firewall (PowerShell as admin):

```powershell
New-NetFirewallRule -DisplayName "livekit-sip SIP" -Direction Inbound -Protocol UDP -LocalPort 5060 -Action Allow
New-NetFirewallRule -DisplayName "livekit-sip SIP TCP" -Direction Inbound -Protocol TCP -LocalPort 5060 -Action Allow
New-NetFirewallRule -DisplayName "livekit-sip RTP" -Direction Inbound -Protocol UDP -LocalPort 10000-10100 -Action Allow
```

Network check: compare your router's WAN IP with `curl https://api.ipify.org`.
Different means CGNAT. That doesn't rule out outbound calls (the audio may still
get back through the path livekit-sip opened), but makes failure more likely.
Check with IT that SIP traffic and `cloudflared` are allowed on the office network.

## 4. Register the trunk with LiveKit

With the telephony stack running (`run-local.bat`, or
`docker compose -f docker-compose.telephony.yml up -d`):

```bash
cd backend
uv run python -m app.scripts.create_sip_trunk
```

It prints `SIP_OUTBOUND_TRUNK_ID=ST_...`; put that in `.env` and restart the API
and agent worker. Re-running it reuses the existing trunk.

## 5. Test call before anything else

Prove two-way audio with one manual call (LiveKit CLI `lk`,
<https://docs.livekit.io/home/cli/>):

```bash
lk sip participant create --url ws://127.0.0.1:7880 --api-key devkey --api-secret secret \
  --trunk ST_... --call +8801XXXXXXXXX --room sip-test --identity phone-test
```

Then join `sip-test` from the browser (e.g. `/dashboard/listen?room=sip-test`) and talk.

| Result | Meaning / next step |
|---|---|
| Phone rings, both sides hear each other | Done. Schedule real calls from the dashboard. |
| Rings, connects, **no or one-way audio** | RTP can't get through NAT. Try Docker Desktop host networking (Settings → Resources → Network), then move the stack to a VPS (below). |
| `403` / call rejected immediately | Bangladesh not enabled in Geo Permissions, or wrong trunk credentials. |
| Times out, never rings | livekit-sip can't reach Twilio, or wrong termination URI. Check `docker compose -f docker-compose.telephony.yml logs livekit-sip`. |

Once it works, pin the image versions you tested (`LIVEKIT_SERVER_IMAGE`,
`LIVEKIT_SIP_IMAGE` in `.env`) instead of `latest`.

## 6. Scheduling a phone call

Dashboard → Schedule → pick the lead and time, enter your number in **Dial phone
number**. At the scheduled time the agent dials it, greets the lead by name, runs
the cold-call script, and hangs up itself (`end_call`) when the conversation is
over. The schedule shows how it ended:

| Status / outcome | When |
|---|---|
| `completed` | Answered and finished (agent or you hung up) |
| `missed` — busy / no answer | SIP 486 / 408, 480, 487 |
| `cancelled` — declined | You rejected the call (603), or **Hang up** in the dashboard |
| `failed` — rejected by carrier / telephony error / agent error | See the table above; agent worker logs have the SIP details |

Follow-ups the agent schedules on a phone call ring the same phone. A dial number
can't be changed after scheduling; delete the call and schedule a new one.

## Dashboard over the internet (Cloudflare tunnel)

`run-local.bat` also opens a "Tunnel" window running a free Cloudflare quick
tunnel (`cloudflared tunnel --url http://localhost:3001`; install with
`winget install Cloudflare.cloudflared`). It prints a new
`https://….trycloudflare.com` URL each run. `SKIP_TUNNEL=1` turns it off;
`CLOUDFLARE_TUNNEL_TOKEN` runs a named tunnel (stable hostname, needs your own
domain on Cloudflare).

- Works through the tunnel: login, dashboard, scheduling phone calls.
- Doesn't: the customer voice/chat widget, browser-mode cold calls, listen-in.
  They need LiveKit's WebRTC media, which the tunnel can't carry. They still work
  on this machine.
- The browser reaches FastAPI through the frontend's `/backend` proxy
  (`next.config.ts`), so leave `NEXT_PUBLIC_FASTAPI_URL` empty in
  `frontend/.env.local`.
- The admin login is now public: use a strong admin password and a long random
  `JWT_SECRET`.

## Moving LiveKit to a VPS

If audio can't get through the office network, run the telephony stack on a small
Linux VPS with a public IP. Either:

- **LiveKit only on the VPS**: `docker compose -f docker-compose.telephony.yml up -d`
  there, set `LIVEKIT_URL=ws://<vps-ip>:7880` in your local `.env`. Backend, agent
  and frontend stay on Windows; the agent connects out to the VPS. Browser calls
  then need the VPS's WebRTC ports reachable too.
- **Everything on the VPS**:
  `docker compose -f docker-compose.yml -f docker-compose.telephony.vm.yml up -d`.
  Uses `livekit.yaml` (public IP, Redis) and host-networked livekit-sip.

On a VPS, always:

- set a strong `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` (secret ≥ 32 chars):
  anyone with them can place calls on your Twilio account;
- allow 5060 and 10000-10100/udp only from Twilio's signalling/media IP ranges
  (SIP scanners find open 5060 ports within minutes);
- never expose Redis.

## Switching carriers later

The agent only knows the LiveKit trunk id. A local Bangladeshi SIP provider or an
Asterisk PBX (for local caller ID and cheaper local rates) only needs a new
outbound trunk with that provider's address and credentials, and a new
`SIP_OUTBOUND_TRUNK_ID`.
