# Telco AI Agent — Design Spec

Date: 2026-10-22
Status: Approved in brainstorming; awaiting written-spec review
Reference UI: `telco_dashboard.html` (static prototype supplied by the user)

## 1. Goal and context

Turn this repository (forked from RealEstateAgent) into a **sales-demo Telco AI agent** for a fictional
Bangladesh mobile operator ("telco"). A prospect sees a customer self-care portal and an operations
admin portal, both on live (seeded) data, and an AI assistant that answers account questions and
performs simulated actions (buy pack, recharge, redeem, open case) by web voice or text chat — with
the portal updating on screen as the agent acts.

### Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Purpose | Sales demo / POC. Seeded mock BSS data, simulated OTP and payments. No real operator integration. |
| Channels | Web voice + text chat. No telephony (SIP/Twilio stays in the repo, unused). |
| Identity | Logged-in persona (5 seeded subscribers). Reads free; writes need simulated OTP + confirm. |
| Frontend | Full rebuild of both portals in Next.js on live data, phased. |
| Language | Bangla-first; mirror the user per turn; Banglish answered in Bangla. |
| Agent scope | Account, packages, recharge, transactions, offers/rewards, support, network, knowledge base, human handoff. |
| RAG | Stays active (Chroma, crawler, Knowledge page, `search_knowledge_base`). Seeded with telco docs. |
| Proactive | In-app nudges via scheduler → notification bell → assistant opens with context. |
| Real-estate code | Deleted (properties, bookings, leads, listing site, `search_apartments`, `listing_focus`, cold-call schedule). |
| Approach | In-place transformation of this repo + a `bss` service seam between tools/APIs and the DB. |
| Frontend skills | Every frontend implementation task must invoke the `frontend-design` and `ui-ux-pro-max` skills. |

### Non-goals

- Real payments, real SMS OTP, real BSS/CRM integration (the `bss` seam makes this possible later, but it is not built).
- Phone calls (inbound or outbound).
- Live transfer to a human agent.
- Multi-tenant / multi-operator support.

## 2. Architecture

```
agent/tools/*  ──►  bss/ (service seam)  ──►  repositories/  ──►  Postgres
api/routes_*   ──►  bss/                       (portal and admin read the same layer)
scheduler/     ──►  bss/ + nudges
```

- **`app/bss/`** — plain functions with Pydantic input/output types, grouped into modules:
  `accounts`, `packages`, `recharge`, `transactions`, `rewards`, `cases`, `network`, `otp`,
  `notifications`, `audit`. No LiveKit imports. Raises typed errors (section 4.4).
- **Tools** are thin: resolve the session's `subscriber_id`, call `bss`, format the result for speech,
  push UI events.
- **Portal and admin APIs** call the same `bss` functions, so the agent and the screen never disagree.
- **Live sync**: after any write, the tool sends `send_text(topic="telco.account_changed")` on the room;
  the portal re-fetches affected cards. Chat and voice share the room, so this works for both.
- Existing pieces kept as-is: LiveKit worker, `gated_agent`, turn gate/judge, `quick_reply`,
  `speech_numbers`, transcripts/conversations, `agent_config` + prompt editor, auth, RAG, run/usage logs.

## 3. Data model

### 3.1 New tables

| Table | Fields |
|---|---|
| `subscribers` | id, msisdn (unique), full_name, plan_type (prepaid/postpaid), district, status (active/suspended), joined_on, reward_points, preferred_language (bn/en) |
| `balances` | subscriber_id (PK/FK), main_balance, postpaid_due, updated_at |
| `packages` | id, code (unique), name, kind (data/voice/bundle/sms), data_mb, minutes, sms, validity_days, price, is_active, tag (e.g. POPULAR, BEST VALUE) |
| `subscriptions` | id, subscriber_id, package_id, data_left_mb, minutes_left, sms_left, activated_at, expires_at, auto_renew, status (active/expired) |
| `usage_events` | id, subscriber_id, kind (data/voice/sms/vas), amount, unit, charge, description, occurred_at |
| `transactions` | id, ref (unique, e.g. TXN-840219), subscriber_id, type (recharge/purchase/redeem), channel (bKash/Nagad/Card/balance/points), amount, target_msisdn, status (success/pending/failed), failure_reason, created_at |
| `support_cases` | id, ref (unique, TC-xxxx), subscriber_id, category, description, priority (normal/high), status (open/in_review/resolved), source (agent/portal/admin), created_at, updated_at, resolved_at |
| `network_incidents` | id, district, area, kind (outage/congestion/maintenance), status (investigating/scheduled/resolved), message, starts_at, ends_at |
| `otp_challenges` | id, subscriber_id, action_id (UUID), purpose, code_hash, expires_at, attempts, consumed_at |
| `notifications` | id, subscriber_id, kind (pack_expiring/low_balance/low_data/case_update), subject_key, payload (JSON), created_at, read_at; unique (subscriber_id, kind, subject_key) |
| `audit_events` | id, subscriber_id, actor (agent/portal/admin), action, action_id, detail (JSON), created_at |

### 3.2 Reshaped tables

- `offers`: drop property links and sale/rent flags; add `package_id` (nullable), `points_cost`,
  `cashback_percent`, `min_recharge`, `audience` (all / plan_type / specific subscribers).
- `conversations`: link to `subscriber_id` instead of client/lead.
- `agent_config`: add `operator_name`, `greeting_nudge`; rename `agency_name` → `operator_name`;
  drop `greeting_coldcall`, `greeting_followup`.

### 3.3 Dropped tables

`clients`, `properties`, `bookings`, `meeting_invites`, `call_schedule` (and their enums), via Alembic migration.

### 3.4 Seed data

- 5 personas:
  1. Samiha Khan — prepaid, Dhaka, 15 GB + 300 min pack expiring in 3 days, ৳486.50.
  2. Rafi Ahmed — prepaid, Chattogram, low balance (< ৳50), one pending Nagad recharge.
  3. Nusrat Mahmud — postpaid, Rajshahi, ৳1,240 bill due.
  4. Tanvir Hasan — prepaid, Sylhet (area with an active congestion incident), low data.
  5. Farhana Islam — prepaid, Gazipur, high reward points, one resolved and one open case.
- About 15 packages across data/voice/bundle/sms (prices and contents as in the reference UI where present).
- 30 days of usage events per persona; transactions including one failed and one pending.
- Network incidents: Sylhet Sadar congestion (investigating), Gazipur maintenance (scheduled).
- Offers: an exclusive pack offer, a points redemption (1 GB for 700 pts), a 10% cashback on ৳200+ recharge.
- KB documents (Markdown, bn + en): package terms, recharge & refund policy, data rollover, SIM replacement,
  roaming FAQ, coverage notes.

## 4. Agent tools and guardrails

### 4.1 Tools

| Group | Tool | Writes | Gate |
|---|---|---|---|
| Account | `get_account_summary()` | no | — |
| | `get_usage_breakdown(period, kind?)` | no | — |
| | `explain_deductions(since?)` | no | — |
| Packages | `search_packages(kind?, max_price?, min_data_gb?, validity?)` | no | — |
| | `recommend_packages()` — ranks by last 30 days of usage | no | — |
| | `purchase_package(package_code, pay_from)` | yes | OTP + confirm |
| Recharge | `start_recharge(amount, channel, msisdn?)` | yes | OTP + confirm |
| Transactions | `lookup_transactions(type?, status?, ref?, days?)` | no | — |
| Rewards | `get_offers_and_points()` | no | — |
| | `redeem_reward(offer_id)` | yes | OTP + confirm |
| Support | `create_support_case(category, description, priority?)` | yes | confirm |
| | `get_case_status(ref?)` | no | — |
| Network | `check_network_status(district?)` — defaults to subscriber's district | no | — |
| KB | `search_knowledge_base(query)` (existing) | no | — |
| Handoff | `request_human_agent(reason)` — opens a high-priority case and tells the user | yes | — |
| Verify | `verify_otp(code)` | yes | — |

### 4.2 Write flow (purchase, recharge, redeem)

1. Tool calls `bss.preview_*`: validates price, sufficient balance, limits. Nothing is executed.
2. Tool creates an OTP challenge bound to a new `action_id`. UI receives a fake SMS toast (`telco.otp_sms`)
   with the 6-digit code and a confirm card (`telco.confirm`: item, price, pay-from) using the existing
   RPC form pattern (as `booking.py` does).
3. User speaks or types the code (`verify_otp`), or taps Confirm and enters it on the card (RPC).
4. `bss.execute_*` runs in one DB transaction, writes an audit event, then the tool sends
   `telco.account_changed`.

The pending action lives in session `userdata`; one at a time. A new write request replaces the pending
one, and the agent says so. `create_support_case` needs a spoken/typed confirmation but no OTP.

### 4.3 Hard rules (enforced in code)

- `execute_*` refuses unless a consumed OTP challenge matches the same `action_id` and subscriber.
- OTP: 3-minute expiry, 3 attempts; then the action is cancelled and the agent explains.
- Recharge: ৳20–1000 per transaction, ৳5000 per day; target number must match `^01[3-9]\d{8}$`.
- Purchase from balance checks funds; if short, the agent offers a recharge first.
- Idempotency: `execute_*` is a no-op if the `action_id` was already executed (guards double-tap and
  voice + chat confirming together).
- Customer reads/writes are always scoped to the session's `subscriber_id`; the only other number
  allowed is a recharge target.
- Every write produces an `audit_events` row.

### 4.4 Errors

`bss` raises typed errors: `InsufficientBalance`, `PackageNotFound`, `LimitExceeded`, `InvalidMsisdn`,
`OtpExpired`, `OtpInvalid`, `OtpAttemptsExceeded`, `NoPendingAction`, `OfferNotEligible`,
`InsufficientPoints`, `CaseNotFound`. Tools map each to a short spoken reason plus a next step, in the
current language. No stack traces reach the user.

## 5. Prompts

### 5.1 Editable fields (`agent_config`, dashboard prompt editor, placeholder validation kept)

| Field | Placeholders |
|---|---|
| `prompt_identity_rules` | `agent_name`, `operator_name`, `current_date`, `timezone`, `knowledge_scope` |
| `greeting_inbound` | `agent_name`, `operator_name`, `customer_name` |
| `greeting_nudge` (new) | `agent_name`, `operator_name`, `customer_name`, `nudge_text` |

### 5.2 Injected per session (not editable)

An account snapshot block: name, masked number, plan type, district, balance (or postpaid due), active
pack with amounts left and expiry, open cases, active incidents in the district. Used for quick answers;
detailed questions and all writes still go through tools.

### 5.3 System prompt outline

1. **Identity** — {agent_name}, digital assistant of {operator_name}, a Bangladesh mobile operator. Warm,
   brief, practical. Demo with sample data.
2. **Language** — Bangla-first; mirror the user each turn; Banglish → Bangla. Numbers and currency
   spoken naturally (existing `speech_numbers`).
3. **Voice style** — 1–2 sentences per turn, no lists or markdown in voice, one question at a time,
   at most 3 packages read aloud then offer more.
4. **Scope** — account, packages, recharge, transactions, offers/rewards, support, network, telco FAQ.
   Anything else: one-line polite redirect.
5. **Grounding** — every number comes from the snapshot or a tool; otherwise call a tool or say unknown.
6. **Actions** — preview → OTP → confirm → execute. State price and pay-from before asking for the
   code. Never claim success before the tool returns success.
7. **Security** — never ask for PIN/password, never repeat an OTP aloud, only the logged-in account.
8. **Troubleshooting playbooks** — recharge not credited, unexpected deduction, slow data, pack not
   activated: which tool first, when to open a case.
9. **Escalation** — anger, repeated failure, explicit human request, or out-of-tool need →
   `request_human_agent`.
10. **Closing** — existing bn/en closing lines.

### 5.4 Internal LLM prompts to rewrite

- `turn_router` — repoint from `search_apartments` arguments to `search_packages` arguments.
- `turn_judge`, `quick_reply` filler, `voice_preview` sample lines — telco wording.

## 6. Frontend

All frontend work must use the `frontend-design` and `ui-ux-pro-max` skills.

### 6.1 Routes

| Area | Route | Data |
|---|---|---|
| Demo login | `/` persona cards; `/login` admin (existing) | `GET /api/demo/personas` |
| Customer portal | `/portal`, `/portal/balance`, `/portal/recharge`, `/portal/packages`, `/portal/offers`, `/portal/support`, `/portal/assistant` | `/api/me/*` → `bss` |
| Admin (new) | `/dashboard` (control center), `/dashboard/subscribers`, `/dashboard/transactions`, `/dashboard/cases`, `/dashboard/network`, `/dashboard/ai-monitor` | `/api/admin/*` → `bss` |
| Admin (kept) | `/dashboard/chatbot`, `/dashboard/knowledge`, `/dashboard/conversations`, `/dashboard/listen`, `/dashboard/offers` (reshaped) | existing |
| Removed | `(site)/home`, `(site)/properties`, `/dashboard/properties`, `/dashboard/bookings`, `/dashboard/leads`, `/dashboard/schedule`, `/dashboard/incoming` | — |

### 6.2 Auth

- Persona login issues a customer JWT carrying `subscriber_id` and role `customer`.
- `/api/token` writes `subscriber_id` (and optional `nudge` id) into LiveKit room/dispatch metadata.
- Admin JWT unchanged (role `admin`).
- Customer endpoints return only the token's own subscriber; admin endpoints require role `admin`.

### 6.3 Assistant UI

- `/portal/assistant`: full chat + voice panel with suggested questions.
- Floating assistant bubble on all other portal pages (reuse the existing widget); the conversation
  continues when the full page is opened.
- Agent-pushed cards (room `send_text` topics):
  `telco.packages` (package cards with Buy → same OTP flow), `telco.confirm` (confirm card + OTP input),
  `telco.otp_sms` (fake SMS toast), `telco.account_changed` (portal re-fetch), `telco.case_created`.

### 6.4 Portal actions without the agent

Recharge, Buy and Redeem buttons call the same `bss` preview/execute endpoints with the same OTP toast.

### 6.5 Admin extras

- Network page can create and resolve incidents (stage an outage live, then ask the agent).
- AI monitor: chats per day, tool calls by intent, fallback rate (turns with no tool and a scope
  redirect), median first response, audit trail. Source: `run_log`, `usage_log`, `audit_events`.
- "Run nudges now" button.

### 6.6 Look

Port the reference UI's tokens and layout: indigo `#4f46e5`, mint `#20b89a`, orange `#ff9b55`,
red `#e45b73`, card radii, sidebar with Customer/Admin modes, light/dark themes, its responsive
breakpoints (1100px, 760px, 390px).

## 7. Nudges

Scheduler job every 15 minutes (plus an admin "run now" endpoint):

| Kind | Rule |
|---|---|
| `pack_expiring` | active subscription expires within 3 days and auto-renew is off |
| `low_balance` | prepaid main balance below ৳50 |
| `low_data` | active pack data left below 10% |
| `case_update` | a case's status changed via admin |

Each writes one `notifications` row, deduped by (subscriber, kind, subject_key). The bell lists unread
notifications; clicking one opens the assistant with `nudge` metadata, and the agent uses `greeting_nudge`.

## 8. Testing

Pytest against real Postgres (as today):

- `bss` unit tests: every preview/execute, balance math, limits, OTP lifecycle (expiry, attempts, reuse),
  idempotency, typed errors.
- Tool tests with a fake `userdata`: writes refused without verified OTP, error → speech mapping,
  correct UI topics emitted.
- API tests: customer cannot read another subscriber; admin-only endpoints enforced; portal path and
  agent path produce the same transaction.
- Nudge tests: each rule fires once; dedupe holds.
- Prompt tests: placeholder validation for the new fields.
- Conversation eval (extend `scripts/router_bench`): about 25 bn/en/Banglish utterances mapped to
  expected tools.
- Frontend: typecheck, lint, and a manual demo-script checklist.

## 9. Phases

Each phase gets its own implementation plan and ends in a runnable state.

1. **Cleanup + data** — remove real-estate code and tables, add telco models + migration, `bss` layer,
   seed data, `bss` tests.
2. **Agent** — tools, OTP/confirm flow, prompts, snapshot injection, internal prompt rewrites, KB seed
   docs, conversation eval.
3. **Customer portal** — persona login, `/portal/*`, assistant page + bubble, agent cards, live sync.
4. **Admin** — new admin pages, incident staging, AI monitor, nudges.

## 10. Risks

- `gated_agent.py` (~1.2k lines) and `entrypoint.py` (~950 lines) likely embed listing-specific logic
  (shortlists, listing focus, booking). Phase 1/2 must map these before deleting; generic turn-taking
  logic stays.
- Voice + chat confirming the same action concurrently — covered by `action_id` idempotency.
- Speaking an OTP aloud is unusual; the prompt forbids the agent repeating it, and the code is only
  shown in the on-screen toast.
