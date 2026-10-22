# Telco Phase 1 — Real-estate Cleanup, Telco Data Model and `bss` Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip the real-estate domain out of the backend and agent, add the telco schema, the `app/bss/` service layer with full tests, and demo seed data, leaving a backend that starts, migrates, seeds and passes its test suite.

**Architecture:** Delete real-estate code bottom-up from its consumers (agent first, then API/repos, then models), replace it with telco SQLAlchemy models plus one Alembic migration, then build `app/bss/` as plain functions over a SQLAlchemy `Session` with Pydantic in/out types and typed errors. The agent is left domain-neutral (only `search_knowledge_base` + end-call); Phase 2 adds the telco tools on top of `bss`.

**Tech Stack:** Python 3.11, SQLAlchemy 2 (sync, `Mapped`), Alembic, Pydantic v2, PostgreSQL 16, pytest against the real DB (`DATABASE_URL` from repo `.env`, Postgres on 5435), uv.

**Spec:** `docs/superpowers/specs/2026-10-22-telco-agent-design.md` (sections 2, 3, 4.2–4.4 and 9 phase 1).

## Global Constraints

- Run everything from `backend/`: tests `uv run pytest -q -p no:cacheprovider`, migrations `uv run alembic upgrade head`. Dev deps need `uv sync --extra dev` once.
- Baseline before Task 1: `1061 passed`. Every task ends with the whole suite green (minus tests the task deletes on purpose).
- Follow existing style: `TimestampedBase` (UUID `id`, `created_at`, `updated_at`) for new tables, `Mapped[...]` + `mapped_column`, `str, enum.Enum` enums stored with `Enum(..., name="<snake>")`, money as `Numeric(12, 2)` ↔ `Decimal`.
- `app/bss/` must not import `livekit`, `app.agent`, or `app.api`. Time comes from a `now: datetime | None = None` parameter (default `datetime.now(timezone.utc)`); local dates use `ZoneInfo(get_settings().agency_timezone)` (`Asia/Dhaka`).
- Recharge limits (spec 4.3): ৳20–1000 per transaction, ৳5000 per subscriber per local day (successful recharges); target number must match `^01[3-9]\d{8}$`.
- OTP (spec 4.3): 6 digits, 3-minute expiry, 3 attempts, stored only as a hash; bound to `(subscriber_id, action_id, purpose, request_hash)`.
- Idempotency: every write takes an `action_id: uuid.UUID`; running the same `action_id` again returns the first result and changes nothing.
- Every write adds one `audit_events` row.
- Phase 1 is backend-only. Frontend pages for removed features (properties, bookings, leads, schedule, offers) will show load errors until Phase 3/4 replace them; do not edit `frontend/` in this phase.
- `agent_config` columns (`agency_name`, `greeting_coldcall`, `greeting_followup`) are NOT changed in Phase 1; Phase 2 reshapes them with the prompts.
- Telephony compose files and LiveKit SIP infra stay; only the outbound cold-call *code* goes.

## Review Focus

1. **Same `action_id` executed twice concurrently (voice and chat confirming together)** — exactly one transaction row and one balance change. Test: `test_execute_purchase_same_action_twice_is_noop` (Task 7) and `test_execute_recharge_same_action_twice_is_noop` (Task 8).
2. **OTP issued for one request, used for a different one** (e.g. code for a ৳69 pack used to buy a ৳799 pack) — refused with `OtpInvalid`. Test: `test_otp_bound_to_request_hash` (Task 6).
3. **Balance exactly equal to price / recharge exactly at limits (৳20, ৳1000, day total ৳5000)** — boundaries are inclusive. Tests: `test_purchase_with_exact_balance_succeeds` (Task 7), `test_recharge_limits_inclusive` (Task 8).
4. **Expired subscriptions and resolved incidents** — never counted as active allowance or outage. Tests: `test_summary_ignores_expired_subscriptions` (Task 5), `test_network_status_ignores_resolved_and_ended` (Task 9).
5. **Recharge target that is not a known subscriber** — succeeds as a demo transaction without crediting anyone and without error. Test: `test_recharge_other_unknown_number` (Task 8).

---

## File Structure

**Delete (agent):** `app/agent/booking.py`, `client_history.py`, `listing_focus.py`, `viewing_context.py`, `phone_dial.py`; `app/agent/tools/book_appointment.py`, `booking_form.py`, `confirm_interest.py`, `reschedule_viewing.py`, `schedule_followup.py`, `search_apartments.py`, `search_offers.py`.

**Delete (backend):** `app/api/routes_bookings.py`, `routes_import.py`, `routes_leads.py`, `routes_offers.py`, `routes_properties.py`, `routes_public.py`, `routes_schedule.py`; `app/repositories/booking_repo.py`, `call_schedule_repo.py`, `client_repo.py`, `invite_repo.py`, `offer_repo.py`, `property_repo.py`; `app/schemas/booking.py`, `call_schedule.py`, `client.py`, `offer.py`, `property.py`; `app/services/excel_import_service.py`, `mock_email_service.py`; `app/models/booking.py`, `call_schedule.py`, `client.py`, `meeting_invite.py`, `offer.py`, `property.py`; `app/data/seed_clients.py`, `seed_offers.py`, `seed_properties.py`, `localities.py`, `listing_images.py`; `app/rag/properties_source.py`; `app/scripts/create_sip_trunk.py`.

**Create:**
```
app/agent/cards.py                 deferred UI cards (generic replacement of the shortlist flush)
app/models/telco.py                all telco tables + enums
migrations/versions/c1a7e0f3b9d2_telco_schema.py
app/bss/__init__.py
app/bss/errors.py                  typed errors
app/bss/types.py                   Pydantic in/out models
app/bss/clock.py                   utc_now(), local_tz(), local_day_bounds()
app/bss/audit.py                   record()
app/bss/otp.py                     issue(), verify(), require_verified()
app/bss/accounts.py                get_account_summary(), get_usage_breakdown(), explain_deductions()
app/bss/packages.py                search(), recommend(), preview_purchase(), execute_purchase()
app/bss/recharge.py                preview_recharge(), execute_recharge()
app/bss/transactions.py            lookup()
app/bss/rewards.py                 get_offers_and_points(), preview_redeem(), execute_redeem()
app/bss/cases.py                   create_case(), get_case_status(), request_human_agent()
app/bss/network.py                 check_network_status()
app/data/seed_telco.py             personas, packages, usage, transactions, cases, incidents, offers
tests/bss_helpers.py               throwaway subscriber/package factories + cleanup
tests/test_bss_otp.py, test_bss_accounts.py, test_bss_packages.py, test_bss_recharge.py,
tests/test_bss_rewards.py, test_bss_cases_network.py, test_seed_telco.py, test_telco_schema.py
```

**Modify:** `app/agent/gated_agent.py`, `prefetch.py`, `persona.py`, `userdata.py`, `session_context.py`, `entrypoint.py`, `transcript.py`, `run_log.py` (comments only), `tools/__init__.py`; `app/main.py`; `app/api/routes_dashboard.py`, `app/schemas/dashboard.py`; `app/repositories/conversation_repo.py`; `app/models/conversation.py`, `app/models/rag.py`, `app/models/__init__.py`; `app/rag/jobs.py`, `app/api/routes_rag.py`, `app/services/rag_service.py` (properties source removal); `app/scheduler/jobs.py`, `app/scheduler/worker.py`; `app/data/seed_all.py`; `README.md` seed line.

---

### Task 0: Put the project under git

**Files:** none created; repo root.

- [ ] **Step 1:** From the repo root run `git init`, confirm `.gitignore` already excludes `.env`, `.env.local`, `backend/.venv/`, `backend/storage/`, `frontend/node_modules/`.
- [ ] **Step 2:** `git status --short | grep -E "\.env$|\.env\.local$"` → Expected: no output (secrets not staged).
- [ ] **Step 3:** Commit everything as the baseline.

```bash
git add -A
git commit -m "chore: baseline import of TelcoAIAgent (forked from RealEstateAgent)"
```

---

### Task 1: Agent tool layer — remove real-estate tools, generic deferred cards, knowledge-only prefetch

**Files:**
- Create: `app/agent/cards.py`
- Modify: `app/agent/gated_agent.py`, `app/agent/prefetch.py`, `app/agent/tools/__init__.py`, `app/agent/userdata.py` (card fields only)
- Delete: `app/agent/listing_focus.py`, `app/agent/viewing_context.py`, `app/agent/tools/search_apartments.py`, `app/agent/tools/search_offers.py`
- Delete tests: `tests/test_listing_focus.py`, `test_viewing_context.py`, `test_property_search.py`, `test_property_types.py`, `test_search_offers.py`
- Test: `tests/test_deferred_cards.py` (rewrite), `tests/test_prefetch.py` (trim)

**Interfaces:**
- Produces: `app.agent.cards.send_card(userdata, topic: str, payload: str) -> None` (async; with `userdata.defer_cards` stores `(topic, payload)` in `userdata.pending_card` instead of sending); `app.agent.cards.flush_pending_card(userdata) -> bool` (async; sends and clears the stored card, returns whether one was sent). Phase 2's `telco.packages` card uses these.
- `SessionUserdata` card fields become: `defer_cards: bool = False`, `pending_card: tuple[str, str] | None = None`. Remove `shown_listings`, `focused_listing`, `pending_cards`, `pending_cards_clear_focus`, `last_search`, `viewing_property_id`.
- `prefetch._LOOKUP_TOOLS` becomes `{"knowledge_base": (search_knowledge_base.TOOL_NAME,)}`; `_run_tool` keeps only the knowledge-base branch; delete `_SEARCH_ARGS`, `_OFFER_ARGS` and the rentals-with-offers early return. `turn_router.py` is untouched (Phase 2 rewrites its schema).
- `gated_agent`: `GatedAgent.llm_node` returns `self._gate.with_filler(self._reply(...), message_id, text)` without `listing_focus`; `_cards_with_speech` calls `cards.flush_pending_card` and checks `userdata.pending_card`; `TurnPublishingAgent.llm_node` is removed (inherits the default); `_search_context(userdata)` returns `None` (keep the `turn_judge.search_context` call site removed, pass `None`).

- [ ] **Step 1: Rewrite `tests/test_deferred_cards.py`** with a fake room participant recording `send_text(payload, topic=...)` calls:

```python
async def test_send_card_immediate_when_not_deferred(): ...
    # defer_cards False -> one send_text("{...}", topic="telco.test"), pending_card is None
async def test_send_card_deferred_then_flushed(): ...
    # defer_cards True -> no send; pending_card == ("telco.test", payload)
    # flush_pending_card -> returns True, one send_text with that topic, pending_card is None
async def test_flush_without_pending_card_returns_false(): ...
```
Keep any existing `GatedAgent._cards_with_speech` tests in that file, re-pointed at `pending_card`.

- [ ] **Step 2:** Run `uv run pytest tests/test_deferred_cards.py -q -p no:cacheprovider` → Expected: FAIL (`ModuleNotFoundError: app.agent.cards`).
- [ ] **Step 3:** Create `app/agent/cards.py` with `send_card` / `flush_pending_card` as specified; update `userdata.py` card fields; edit `gated_agent.py` and `prefetch.py` as in Interfaces; drop deleted tools from `tools/__init__.py` (`ALL_TOOLS` / `INBOUND_TOOLS` keep only what remains; Task 2 removes the rest); delete the listed modules and tests; remove `search_apartments`/`search_offers` cases from `tests/test_prefetch.py` and `tests/test_prompts.py` imports.
- [ ] **Step 4:** `uv run python -c "import app.agent.gated_agent, app.agent.prefetch"` → Expected: no output. Then run the full suite → Expected: all pass.
- [ ] **Step 5: Commit** — `git commit -am "refactor(agent): generic deferred cards, drop listing tools and focus"` (add new/deleted files with `git add -A`).

---

### Task 2: Agent session layer — remove bookings, client history, cold calls

**Files:**
- Modify: `app/agent/userdata.py`, `session_context.py`, `persona.py`, `entrypoint.py`, `transcript.py`, `tools/__init__.py`, `app/scheduler/jobs.py`, `app/scheduler/worker.py`
- Delete: `app/agent/booking.py`, `client_history.py`, `phone_dial.py`, `tools/book_appointment.py`, `booking_form.py`, `confirm_interest.py`, `reschedule_viewing.py`, `schedule_followup.py`, `app/scripts/create_sip_trunk.py`
- Delete tests: `test_book_appointment.py`, `test_booking_form.py`, `test_client_history.py`, `test_phone_dial.py`, `test_reschedule_viewing.py`, `test_schedule_decline.py`, `test_schedule_followup.py`, `test_schedule_phone.py`
- Test: `tests/test_session_context.py` (create), `tests/test_prompts.py`, `tests/test_greeting_guard.py` (update)

**Interfaces:**
- `Channel` keeps only `inbound_chat`.
- `SessionUserdata` drops `client`, `client_id`, `call_schedule_id`, `history`, `pending_booking`, `upcoming_viewing`, `BookingState`, `PendingBooking`, `UpcomingViewing`; adds `subscriber_id: UUID | None = None` and `nudge_id: UUID | None = None`. `is_phone_call` stays (always `False` for now; Phase 2 may drop it).
- `session_context.resolve(raw_metadata, room) -> SessionUserdata` reads `subscriber_id` and `nudge_id` (UUID strings; malformed → `None`) and `visitor_id` as today. It does not touch the DB.
- `persona.build_system_prompt(...)` keeps its signature minus client/viewing inputs and assembles: rendered `prompt_identity_rules` + a neutral `_INBOUND_TASK` ("Help the customer with their mobile account questions using your tools; if you can't, say so briefly.") + `_BROWSER_END_NOTE` + knowledge scope. Delete `_BOOKING_STEPS`, `_OFFERS_RULE`, `_SEARCH_RESULTS_RULE`, `_OUTBOUND_TASK`, `_COLD_CALL_OPENING`, `_FOLLOWUP_CALL_OPENING`, `_VIEWING_FOLLOWUP`, `_PHONE_CALL_NOTE`, `_SHOW_LISTING_RULE`, `_END_REASONS_OUTBOUND`, `_phone_booking_instruction`, `_client_criteria_summary`. Phase 2 writes the telco prompt.
- `entrypoint`: delete `_run_phone_call`, `_mark_call_schedule_*`, `_save_last_search`, `_follow_viewed_listing`, `_serve_booking_form`, the ringing/cold-call branch of `entrypoint()`; `_session_tools` returns `[end_call]` + `search_knowledge_base` when RAG is enabled; `_greet` always uses `greeting_inbound`.
- `transcript`: on close, store `subscriber_id` instead of `client_id` (the column rename lands in Task 4 — until then pass it as `client_id=None`; Task 4 switches the keyword).
- Scheduler: remove `poll_due_calls` and `_dispatch_call`; worker log line becomes `"scheduler started: conversation sweep every 10m, embedding jobs every 5s"`.

- [ ] **Step 1: Write `tests/test_session_context.py`:**

```python
def test_resolve_reads_subscriber_and_nudge():
    sid, nid = uuid4(), uuid4()
    u = resolve(json.dumps({"subscriber_id": str(sid), "nudge_id": str(nid)}), room=FakeRoom())
    assert u.subscriber_id == sid and u.nudge_id == nid and u.channel == Channel.inbound_chat

def test_resolve_bad_ids_become_none():
    u = resolve(json.dumps({"subscriber_id": "nope", "nudge_id": 7}), room=FakeRoom())
    assert u.subscriber_id is None and u.nudge_id is None

def test_resolve_no_metadata_is_anonymous_chat():
    assert resolve(None, room=FakeRoom()).subscriber_id is None
```
- [ ] **Step 2:** Run it → Expected: FAIL (`unexpected keyword` / attribute errors).
- [ ] **Step 3:** Make the Interfaces changes; delete listed files and tests; fix `test_prompts.py` / `test_greeting_guard.py` to the trimmed prompt (drop assertions about booking, offers, cold-call and viewing text; keep placeholder-validation tests).
- [ ] **Step 4:** `uv run python -c "import app.agent.entrypoint, app.scheduler.worker"` → no output; full suite → all pass; `grep -rnE "booking|client_history|cold.?call|viewing" app/agent app/scheduler` → Expected: no matches except unrelated words in `turn_router.py` (Phase 2).
- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor(agent): drop bookings, client history and outbound calls"`.

---

### Task 3: Remove real-estate API, repositories, schemas, services, seeds and the RAG properties source

**Files:**
- Delete: all backend files listed under *Delete (backend)* in File Structure except the `app/models/*` files (Task 4 removes those).
- Modify: `app/main.py` (title `"Telco AI Agent Backend"`, routers: auth, dashboard, agent_config, conversations, public_conversations, rag); `app/api/routes_dashboard.py` + `app/schemas/dashboard.py` (remove `/recent-bookings`, `RecentBooking`, and the `pending_calls_today` / `active_listings` fields from `DashboardSummary`; keep conversation and RAG endpoints); `app/rag/jobs.py`, `app/api/routes_rag.py`, `app/services/rag_service.py` (remove the properties source branch, `sync_properties` service and `POST /sources/properties/sync`); `app/data/seed_all.py` (temporarily seeds nothing but prints `"Seeded 0 rows."`; Task 10 wires telco seeding); `app/repositories/conversation_repo.py` (drop the `Client` join: list rows become `(conversation, None, first user message)`; delete `link_client`, `recent_for_client`).
- Delete tests: `test_bookings_api.py`, `test_offers_api.py`, `test_public_listings.py`, `test_localities.py`, `offer_helpers.py`, `reserved_phone.py` (if only used by deleted tests — check with grep first); update `test_dashboard_series.py`, `test_embedding_jobs.py`, `test_rag.py`, `test_conversations_api.py` for the removed fields/source.

**Interfaces:**
- Produces: `DashboardSummary` without `pending_calls_today` and `active_listings`; `GET /api/rag/sources/properties/sync` gone; `conversation_repo.list_conversations` row shape `(Conversation, str | None, str | None)` unchanged in type.

- [ ] **Step 1:** Add to `tests/test_dashboard_series.py`:

```python
def test_summary_has_no_real_estate_fields(api):
    body = api.get("/api/dashboard/summary").json()
    assert "active_listings" not in body and "pending_calls_today" not in body
```
And to `tests/test_rag.py`: `assert api.post("/api/rag/sources/properties/sync").status_code == 404`. (Use the existing route prefixes; confirm with `grep -n "prefix" app/api/routes_dashboard.py app/api/routes_rag.py`.)
- [ ] **Step 2:** Run both files → Expected: FAIL.
- [ ] **Step 3:** Apply the deletions and modifications.
- [ ] **Step 4:** `uv run python -c "from app.main import app"` → no output; `grep -rnE "app\.(repositories|schemas)\.(property|client|booking|call_schedule|offer)|properties_source" app tests` → no matches; full suite → all pass.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: remove real-estate API, repos, schemas, seeds and properties RAG source"`.

---

### Task 4: Telco models and schema migration

**Files:**
- Create: `app/models/telco.py`, `migrations/versions/c1a7e0f3b9d2_telco_schema.py` (`down_revision = 'b5c9e2a7d3f1'`)
- Modify: `app/models/__init__.py`, `app/models/conversation.py`, `app/models/rag.py`, `app/agent/transcript.py`, `app/repositories/conversation_repo.py`
- Delete: `app/models/booking.py`, `call_schedule.py`, `client.py`, `meeting_invite.py`, `offer.py`, `property.py`
- Test: `tests/test_telco_schema.py`

**Interfaces (produces — every later task uses these names):**

Enums (`str, enum.Enum`, DB type name in brackets):
`PlanType` [plan_type]: prepaid, postpaid · `SubscriberStatus` [subscriber_status]: active, suspended · `PackageKind` [package_kind]: data, voice, bundle, sms · `SubscriptionStatus` [subscription_status]: active, expired · `UsageKind` [usage_kind]: data, voice, sms, vas · `TxnType` [txn_type]: recharge, purchase, redeem · `TxnChannel` [txn_channel]: bkash, nagad, card, balance, points · `TxnStatus` [txn_status]: success, pending, failed · `CasePriority` [case_priority]: normal, high · `CaseStatus` [case_status]: open, in_review, resolved · `CaseSource` [case_source]: agent, portal, admin · `IncidentKind` [incident_kind]: outage, congestion, maintenance · `IncidentStatus` [incident_status]: investigating, scheduled, resolved · `NotificationKind` [notification_kind]: pack_expiring, low_balance, low_data, case_update · `OfferAudience` [offer_audience]: all, prepaid, postpaid · `Actor` [audit_actor]: agent, portal, admin, system.

Tables (all `TimestampedBase` unless noted; FKs to `subscribers.id` are `ondelete="CASCADE"`):

| Model / table | Columns beyond id/created_at/updated_at |
|---|---|
| `Subscriber` / `subscribers` | msisdn `String(11)` unique not null, full_name `String(120)`, plan_type, district `String(60)`, status default active, joined_on `Date`, reward_points `Integer` default 0, preferred_language `String(2)` default "bn" |
| `Balance` / `balances` (plain `Base`, PK = `subscriber_id`) | main_balance `Numeric(12,2)` default 0, postpaid_due `Numeric(12,2)` default 0, updated_at |
| `Package` / `packages` | code `String(32)` unique, name `String(120)`, kind, data_mb `Integer` default 0, minutes `Integer` default 0, sms `Integer` default 0, validity_days `Integer`, price `Numeric(12,2)`, is_active `Boolean` default true, tag `String(32)` null |
| `Subscription` / `subscriptions` | subscriber_id, package_id FK `packages.id`, data_left_mb, minutes_left, sms_left (`Integer`), activated_at, expires_at (`DateTime(tz)`), auto_renew `Boolean` default false, status default active; index (subscriber_id, status) |
| `UsageEvent` / `usage_events` | subscriber_id, kind, amount `Numeric(12,2)`, unit `String(8)` ("MB"/"min"/"sms"/"item"), charge `Numeric(12,2)` default 0, description `String(160)`, occurred_at; index (subscriber_id, occurred_at) |
| `Transaction` / `transactions` | ref `String(16)` unique, subscriber_id, action_id `UUID` unique null, type, channel, amount `Numeric(12,2)`, target_msisdn `String(11)` null, package_id FK null, offer_id FK null, cashback `Numeric(12,2)` default 0, status, failure_reason `String(160)` null |
| `SupportCase` / `support_cases` | ref `String(12)` unique, subscriber_id, action_id `UUID` unique null, category `String(60)`, description `Text`, priority default normal, status default open, source, resolved_at null |
| `NetworkIncident` / `network_incidents` (no subscriber FK) | district `String(60)`, area `String(120)`, kind, status, message `Text`, starts_at, ends_at null |
| `OtpChallenge` / `otp_challenges` | subscriber_id, action_id `UUID` unique, purpose `String(32)`, request_hash `String(64)`, code_hash `String(64)`, expires_at, attempts `Integer` default 0, consumed_at null |
| `Notification` / `notifications` | subscriber_id, kind, subject_key `String(80)`, payload `JSONB`, read_at null; unique (subscriber_id, kind, subject_key) |
| `AuditEvent` / `audit_events` | subscriber_id null, actor, action `String(40)`, action_id `UUID` null, detail `JSONB` |
| `Offer` / `offers` | title `String(160)`, description `Text` null, terms `Text` null, package_id FK null, points_cost `Integer` null, cashback_percent `Numeric(5,2)` null, cashback_cap `Numeric(12,2)` null, min_recharge `Numeric(12,2)` null, audience default all, starts_on/ends_on `Date` null, is_active default true |

Sequences: `txn_ref_seq START 840220` → refs `f"TXN-{nextval}"`; `case_ref_seq START 2049` → refs `f"TC-{nextval}"`.

Migration `upgrade()` order: drop `offer_properties`, `offers`, `meeting_invites`, `bookings`, `call_schedule`, `properties`, and (after removing the FK) `clients`; drop their enum types (`offer_type`, `invite_status`, `recipient_type`, `booking_status`, `booking_channel`, `call_status`, `property_type`, `listing_type`, `lead_status`, `rent_or_buy` — confirm names with `grep -rn "name=\"" app/models` on the pre-Task-4 tree); delete `rag_sources` rows of type `properties` and their `embedding_jobs` of type `sync_properties`, then recreate `rag_source_type` and `embedding_job_type` enums without those values (same rename/create/alter/drop pattern as `b5c9e2a7d3f1`); on `conversations` drop `client_id`, add `subscriber_id UUID NULL REFERENCES subscribers(id) ON DELETE SET NULL` + index; create all telco enums, tables and both sequences. `downgrade()` raises `NotImplementedError("telco schema is one-way")`.

Code follow-ups: `Conversation.client_id` → `subscriber_id`; `conversation_repo.create/end(..., subscriber_id=...)` and `list_conversations` joins `Subscriber.full_name`; `transcript` passes `subscriber_id=userdata.subscriber_id`; `RagSourceType`/`EmbeddingJobType` lose `properties`/`sync_properties`.

- [ ] **Step 1: Write `tests/test_telco_schema.py`:**

```python
def test_alembic_head_matches_models():
    # `alembic check` exits 0 when models and DB agree
    r = subprocess.run(["uv", "run", "alembic", "check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

def test_real_estate_tables_gone(db):
    names = set(inspect(db.bind).get_table_names())
    assert not names & {"properties", "clients", "bookings", "call_schedule", "meeting_invites", "offer_properties"}

def test_ref_sequences_start_values(db):
    # nextval in a rolled-back transaction still advances; only check the format
    ref = db.execute(text("SELECT 'TXN-' || nextval('txn_ref_seq')")).scalar()
    assert re.fullmatch(r"TXN-\d{6,}", ref)
```
(`db` fixture: add to `tests/conftest.py` — yields `SessionLocal()`, rolls back and closes.)
- [ ] **Step 2:** Run → Expected: FAIL (`alembic check` reports differences / missing tables).
- [ ] **Step 3:** Write `app/models/telco.py`, the migration, the model/repo/transcript follow-ups; update `app/models/__init__.py` exports (drop removed models, add all telco models and enums).
- [ ] **Step 4:** `uv run alembic upgrade head` → ends with `Running upgrade b5c9e2a7d3f1 -> c1a7e0f3b9d2`; run the test file → PASS; full suite → all pass.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(db): telco schema, drop real-estate tables"`.

---

### Task 5: `bss` foundation and accounts

**Files:**
- Create: `app/bss/__init__.py`, `errors.py`, `types.py`, `clock.py`, `audit.py`, `accounts.py`, `network.py` (only `active_incidents_query` for now), `tests/bss_helpers.py`, `tests/test_bss_accounts.py`

**Interfaces:**
- `errors.py`: `class BssError(Exception)` with `code: str` class attribute; subclasses (code = snake_case of name): `SubscriberNotFound`, `InsufficientBalance`, `PackageNotFound`, `LimitExceeded`, `InvalidMsisdn`, `OtpExpired`, `OtpInvalid`, `OtpAttemptsExceeded`, `NoPendingAction`, `OfferNotEligible`, `InsufficientPoints`, `CaseNotFound`. Each carries an English `message` used in logs; Phase 2 maps `code` to spoken bn/en text.
- `clock.py`: `utc_now() -> datetime`, `local_tz() -> ZoneInfo`, `local_day_bounds(now: datetime) -> tuple[datetime, datetime]` (UTC bounds of `now`'s local day).
- `audit.py`: `record(db, *, actor: Actor, action: str, subscriber_id: UUID | None, action_id: UUID | None = None, detail: dict | None = None) -> None` (adds, does not commit).
- `types.py` (Pydantic, `model_config = ConfigDict(from_attributes=True)`): `Allowance(data_left_mb: int, minutes_left: int, sms_left: int)`; `SubscriptionView(package_code, package_name, data_left_mb, minutes_left, sms_left, expires_at: datetime, auto_renew: bool)`; `AccountSummary(subscriber_id: UUID, full_name, masked_msisdn, plan_type: PlanType, district, main_balance: Decimal, postpaid_due: Decimal, reward_points: int, totals: Allowance, subscriptions: list[SubscriptionView], nearest_expiry: datetime | None, open_cases: int, district_incidents: int)`; `UsageTotals(kind: UsageKind, amount: Decimal, unit: str, charge: Decimal)`; `UsageBreakdown(period_days: int, totals: list[UsageTotals], daily: list[tuple[date, Decimal]])` (daily = data MB per local day, oldest first); `Deduction(occurred_at: datetime, description: str, amount: Decimal, source: Literal["usage", "purchase"])`.
- `accounts.py`:
  - `get_account_summary(db, subscriber_id, *, now=None) -> AccountSummary` — only subscriptions with `status == active and expires_at > now`; `masked_msisdn` = first 3 + `"••••"` + last 4 (e.g. `017••••2841`); `open_cases` counts status ≠ resolved; `district_incidents` uses the same rule as `network.check_network_status` (Task 9) — implement the query helper `network.active_incidents_query(district, now)` here in `network.py` now and reuse it in Task 9. Raises `SubscriberNotFound`.
  - `get_usage_breakdown(db, subscriber_id, *, period_days: int = 30, kind: UsageKind | None = None, now=None) -> UsageBreakdown` — `period_days` must be 7 or 30 else `ValueError`.
  - `explain_deductions(db, subscriber_id, *, since: datetime | None = None, now=None) -> list[Deduction]` — default `since = now - 7 days`; usage events with `charge > 0` plus successful `purchase` transactions paid from `balance`, newest first, max 20.
- `tests/bss_helpers.py`: pytest fixture `bss_world` yielding a helper with `subscriber(**overrides) -> Subscriber` (msisdn from the reserved block `0199900xxxx`, name prefixed `PYTEST `, creates a `Balance` row), `package(**overrides) -> Package` (code prefix `PT-`), `subscription(sub, pkg, **overrides)`, `usage(sub, kind, amount, charge=0, at=...)`, `incident(**overrides)`; teardown deletes subscribers by msisdn prefix `01999`, packages by code prefix `PT-`, incidents by area prefix `PYTEST`, offers by title prefix `PYTEST`. Register it via `pytest_plugins = ["bss_helpers"]` in `tests/conftest.py`.

- [ ] **Step 1: Write `tests/test_bss_accounts.py`:**

```python
def test_summary_totals_and_masking(bss_world, db):
    s = bss_world.subscriber(msisdn="01999002841", main_balance=Decimal("486.50"))
    p = bss_world.package(data_mb=15360, minutes=300, validity_days=30)
    bss_world.subscription(s, p, data_left_mb=8602, minutes_left=182, expires_in_days=3)
    out = accounts.get_account_summary(db, s.id)
    assert out.masked_msisdn == "019••••2841"
    assert out.main_balance == Decimal("486.50")
    assert out.totals == Allowance(data_left_mb=8602, minutes_left=182, sms_left=0)
    assert out.nearest_expiry is not None

def test_summary_ignores_expired_subscriptions(bss_world, db):
    s = bss_world.subscriber(); p = bss_world.package(data_mb=1024)
    bss_world.subscription(s, p, data_left_mb=500, expires_in_days=-1)
    assert accounts.get_account_summary(db, s.id).totals.data_left_mb == 0

def test_summary_unknown_subscriber(db):
    with pytest.raises(SubscriberNotFound): accounts.get_account_summary(db, uuid4())

def test_usage_breakdown_7_days_daily_series(bss_world, db):
    # 3 data events on 3 different local days inside 7 days, 1 outside
    ...; out = accounts.get_usage_breakdown(db, s.id, period_days=7)
    assert len(out.daily) == 7 and sum(v for _, v in out.daily) == Decimal("300")

def test_usage_breakdown_rejects_other_periods(bss_world, db):
    with pytest.raises(ValueError): accounts.get_usage_breakdown(db, s.id, period_days=14)

def test_explain_deductions_only_charged_items(bss_world, db):
    # one charge=0 data event, one charge=2.50 vas event -> one Deduction with amount 2.50
```
- [ ] **Step 2:** Run → Expected: FAIL (`ModuleNotFoundError: app.bss`).
- [ ] **Step 3:** Implement the Interfaces.
- [ ] **Step 4:** Run the file → PASS; full suite → all pass.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(bss): errors, types, audit and account queries"`.

---

### Task 6: OTP challenges

**Files:**
- Create: `app/bss/otp.py`, `tests/test_bss_otp.py`

**Interfaces:**
- `request_hash(purpose: str, payload: dict) -> str` — sha256 hex of `purpose + json.dumps(payload, sort_keys=True, default=str)`.
- `issue(db, *, subscriber_id, action_id, purpose: str, payload: dict, now=None) -> str` — creates (or replaces an unconsumed one for the same `action_id`) an `OtpChallenge` with `expires_at = now + 3 min`, `code_hash = sha256(f"{action_id}:{code}")`; returns the 6-digit plaintext code (`secrets.randbelow(10**6)`, zero-padded). Commits.
- `verify(db, *, subscriber_id, action_id, purpose, payload, code: str, now=None) -> None` — raises `NoPendingAction` (no challenge for this subscriber+action), `OtpExpired`, `OtpAttemptsExceeded` (attempts already ≥ 3), `OtpInvalid` (wrong code or `request_hash` mismatch; increments `attempts`); on success sets `consumed_at`. Commits. A second `verify` after success is a no-op.
- `require_verified(db, *, subscriber_id, action_id, purpose, payload) -> None` — raises `OtpInvalid` unless a consumed challenge matches all four. Used by every `execute_*`.

- [ ] **Step 1: Write `tests/test_bss_otp.py`:**

```python
def test_issue_and_verify_happy_path(...): code = otp.issue(...); otp.verify(..., code=code); otp.require_verified(...)
def test_wrong_code_counts_attempts_then_locks(...):
    # 3 wrong verifies -> OtpInvalid x3; 4th (even correct) -> OtpAttemptsExceeded
def test_expired_after_three_minutes(...):  # verify with now=issued+181s -> OtpExpired
def test_otp_bound_to_request_hash(...):
    # issued for {"package_code": "PT-A"}, verify with payload {"package_code": "PT-B"} -> OtpInvalid
def test_require_verified_without_verify_raises(...): -> OtpInvalid
def test_code_never_stored_in_plaintext(...): assert code not in row.code_hash
def test_verify_unknown_action(...): -> NoPendingAction
```
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; full suite green.
- [ ] **Step 5: Commit** — `git commit -am "feat(bss): OTP challenges bound to action and request"` (with `git add -A`).

---

### Task 7: Packages — search, recommend, purchase

**Files:**
- Create: `app/bss/packages.py`, `tests/test_bss_packages.py`
- Modify: `app/bss/types.py`

**Interfaces:**
- Types: `PackageView(code, name, kind: PackageKind, data_mb, minutes, sms, validity_days, price: Decimal, tag: str | None)`; `Recommendation(package: PackageView, reason: str)`; `PurchaseRequest(package_code: str, pay_from: TxnChannel)`; `PurchaseQuote(request: PurchaseRequest, package: PackageView, pay_from: TxnChannel, price: Decimal, balance_after: Decimal | None)`; `PurchaseResult(transaction_ref: str, package: PackageView, expires_at: datetime, main_balance: Decimal, postpaid_due: Decimal)`.
- `search(db, *, kind=None, max_price: Decimal | None = None, min_data_gb: float | None = None, validity_days: int | None = None) -> list[PackageView]` — active only, ordered by price asc.
- `recommend(db, subscriber_id, *, now=None, limit: int = 3) -> list[Recommendation]` — algorithm:
  1. `need_data` = data MB used in the last 30 days, `need_min` = voice minutes in the last 30 days.
  2. Candidates: active packages of kind `bundle` if both needs > 0, `data` if only data, `voice` if only minutes; all active if neither.
  3. For each: `f = 30 / validity_days`; `coverage = mean(min(1, data_mb*f/need_data) if need_data else 1, min(1, minutes*f/need_min) if need_min else 1)`; `monthly_cost = price * f`.
  4. Sort by `(-round(coverage, 1), monthly_cost)`; take `limit`. `reason` = `f"Covers about {round(coverage*100)}% of your last 30 days' use for ৳{monthly_cost:.0f}/month"`.
- `preview_purchase(db, subscriber_id, req: PurchaseRequest) -> PurchaseQuote` — `PackageNotFound` if missing/inactive; `pay_from` must be one of `balance, bkash, nagad, card` else `ValueError`; prepaid + balance: `InsufficientBalance` if `main_balance < price` (equal is fine), `balance_after = main_balance - price`; postpaid + balance: added to bill, `balance_after = None`; external channels: `balance_after = None`.
- `execute_purchase(db, subscriber_id, req, *, action_id, actor: Actor, now=None) -> PurchaseResult` — if a `Transaction` with this `action_id` exists, return the result rebuilt from it; else `otp.require_verified(purpose="purchase", payload=req.model_dump(mode="json"))`, re-run preview checks, lock the balance row (`with_for_update`), deduct (prepaid balance) or add to `postpaid_due` (postpaid balance), create a `Subscription` (allowances = package values, `expires_at = now + validity_days`), a success `Transaction` (`type=purchase`, ref from `txn_ref_seq`), an audit event `"purchase"`; commit. An `IntegrityError` on the `action_id` unique constraint (concurrent duplicate) → rollback and return the existing result.

- [ ] **Step 1: Write `tests/test_bss_packages.py`:**

```python
def test_search_filters_and_sorts(bss_world, db): ...  # kind/max_price/min_data_gb/validity, ascending price
def test_search_excludes_inactive(bss_world, db): ...
def test_recommend_bundle_for_data_and_voice_user(bss_world, db): ...  # top result kind == bundle, 3 results max
def test_recommend_data_only_user_gets_data_packs(bss_world, db): ...
def test_preview_insufficient_balance(bss_world, db): ...  # balance 50, price 69 -> InsufficientBalance
def test_purchase_with_exact_balance_succeeds(bss_world, db): ...  # balance == price -> main_balance 0
def test_execute_requires_verified_otp(bss_world, db): ...  # -> OtpInvalid
def test_execute_purchase_creates_subscription_and_txn(bss_world, db): ...
    # after issue+verify: one Transaction(type=purchase, status=success, ref matches r"TXN-\d+"),
    # one active Subscription with full allowances, balance reduced, one audit_events row action="purchase"
def test_execute_purchase_same_action_twice_is_noop(bss_world, db): ...
    # second call returns same transaction_ref; still one txn; balance deducted once
def test_postpaid_balance_purchase_adds_to_bill(bss_world, db): ...
```
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; full suite green.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(bss): package search, recommendation and purchase"`.

---

### Task 8: Recharge and transaction lookup

**Files:**
- Create: `app/bss/recharge.py`, `app/bss/transactions.py`, `tests/test_bss_recharge.py`
- Modify: `app/bss/types.py`

**Interfaces:**
- Types: `RechargeRequest(amount: Decimal, channel: TxnChannel, target_msisdn: str | None = None)`; `RechargeQuote(request, target_msisdn: str, is_own_number: bool, cashback: Decimal)`; `RechargeResult(transaction_ref, amount, cashback, target_msisdn, main_balance: Decimal | None, postpaid_due: Decimal | None)`; `TransactionView(ref, type, channel, amount, target_msisdn, status, failure_reason, created_at, package_name: str | None)`.
- `preview_recharge(db, subscriber_id, req, *, now=None) -> RechargeQuote` — `channel` must be `bkash|nagad|card` else `ValueError`; target defaults to own msisdn; `InvalidMsisdn` unless `^01[3-9]\d{8}$` (strip spaces/dashes and a leading `+88`/`88` first); `LimitExceeded` if `amount < 20 or amount > 1000` or today's successful recharges by this subscriber + amount > 5000; cashback = best eligible active offer with `cashback_percent` (`amount >= min_recharge`, audience matches, date range includes local today): `min(amount * pct / 100, cashback_cap)`, rounded to 2 dp; cashback only for own-number recharges.
- `execute_recharge(db, subscriber_id, req, *, action_id, actor, now=None) -> RechargeResult` — same idempotency + `require_verified(purpose="recharge", ...)` pattern as `execute_purchase`; target is a known prepaid subscriber → `main_balance += amount` (+ cashback if own); known postpaid → `postpaid_due = max(0, postpaid_due - amount)`; unknown number → nothing credited. Transaction `type=recharge`, `status=success`, `cashback` stored; audit `"recharge"`.
- `transactions.lookup(db, subscriber_id, *, type=None, status=None, ref=None, days: int = 30, now=None, limit: int = 10) -> list[TransactionView]` — own transactions only, newest first; `ref` match is case-insensitive and ignores the `days` window.

- [ ] **Step 1: Write `tests/test_bss_recharge.py`:**

```python
def test_recharge_limits_inclusive(...):  # 20 ok, 1000 ok, 19.99 and 1000.01 -> LimitExceeded
def test_daily_cap_5000(...):  # 4 x 1000 + 1000 ok; next 20 -> LimitExceeded
def test_msisdn_normalisation_and_validation(...):  # "+8801712-342841" ok; "0121234567" -> InvalidMsisdn
def test_execute_recharge_credits_own_prepaid_with_cashback(...):  # 10% offer cap 30, recharge 500 -> +500 +30
def test_recharge_other_unknown_number(...):  # success txn, own balance unchanged, cashback 0
def test_recharge_postpaid_reduces_due(...):
def test_execute_recharge_same_action_twice_is_noop(...):
def test_lookup_scoped_to_subscriber_and_ref(...):  # another subscriber's txn never returned; ref "txn-..." matches
```
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; full suite green.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(bss): recharge with limits and cashback, transaction lookup"`.

---

### Task 9: Rewards, support cases, network

**Files:**
- Create: `app/bss/rewards.py`, `app/bss/cases.py`, `tests/test_bss_rewards.py`, `tests/test_bss_cases_network.py`
- Modify: `app/bss/network.py` (from Task 5), `app/bss/types.py`

**Interfaces:**
- Types: `OfferView(id: UUID, title, description, terms, points_cost: int | None, cashback_percent, cashback_cap, min_recharge, package: PackageView | None, ends_on: date | None)`; `OffersAndPoints(reward_points: int, offers: list[OfferView])`; `RedeemQuote(offer: OfferView, points_after: int)`; `RedeemResult(transaction_ref, offer_title, reward_points: int, expires_at: datetime | None)`; `CaseView(ref, category, description, priority, status, source, created_at, updated_at, resolved_at)`; `IncidentView(district, area, kind, status, message, starts_at, ends_at)`.
- `rewards.get_offers_and_points(db, subscriber_id, *, now=None) -> OffersAndPoints` — active, in date range (local today), audience `all` or matching plan type.
- `rewards.preview_redeem(db, subscriber_id, offer_id) -> RedeemQuote` — `OfferNotEligible` if not in the list above or `points_cost is None`; `InsufficientPoints` if points < cost (equal is fine).
- `rewards.execute_redeem(db, subscriber_id, offer_id, *, action_id, actor, now=None) -> RedeemResult` — idempotent; `require_verified(purpose="redeem", payload={"offer_id": str(offer_id)})`; deduct points; if the offer has a package, create its subscription; transaction `type=redeem, channel=points, amount=0`; audit `"redeem"`.
- `cases.create_case(db, subscriber_id, *, category, description, priority=CasePriority.normal, source: CaseSource, action_id) -> CaseView` — idempotent on `action_id`; ref from `case_ref_seq`; audit `"case_created"`. No OTP (spec 4.1).
- `cases.request_human_agent(db, subscriber_id, *, reason, source, action_id) -> CaseView` — `create_case(category="human_handoff", description=reason, priority=high)`.
- `cases.get_case_status(db, subscriber_id, *, ref: str | None = None, limit: int = 5) -> list[CaseView]` — with `ref`: that case if it is the subscriber's, else `CaseNotFound`; without: subscriber's cases, unresolved first, then newest.
- `network.check_network_status(db, district: str, *, now=None) -> list[IncidentView]` — `active_incidents_query`: case-insensitive district match, `status != resolved`, `starts_at <= now + 1 day` (so scheduled maintenance tomorrow shows), `ends_at is null or ends_at > now`.

- [ ] **Step 1: Write tests:**

```python
# test_bss_rewards.py
def test_offers_filtered_by_audience_and_dates(...)
def test_redeem_exact_points_succeeds_and_grants_package(...)  # points == cost -> 0 left, new subscription
def test_redeem_insufficient_points(...)
def test_redeem_requires_otp(...)
def test_redeem_same_action_twice_is_noop(...)
# test_bss_cases_network.py
def test_create_case_ref_and_idempotency(...)  # ref r"TC-\d+"; same action_id -> same ref, one row
def test_human_handoff_is_high_priority(...)
def test_case_status_scoped_to_subscriber(...)  # other subscriber's ref -> CaseNotFound
def test_case_status_unresolved_first(...)
def test_network_status_ignores_resolved_and_ended(...)
def test_network_status_includes_maintenance_within_a_day(...)
```
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS; full suite green.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(bss): rewards, support cases and network status"`.

---

### Task 10: Demo seed data

**Files:**
- Create: `app/data/seed_telco.py`, `tests/test_seed_telco.py`
- Modify: `app/data/seed_all.py`, `README.md` (seed description line)

**Interfaces:**
- `seed_telco.seed(db, *, now=None) -> dict[str, int]` — flushes but does not commit (`seed_all.main()` commits); idempotent: does nothing and returns zeros if any non-test subscriber (msisdn not starting `01999`) exists. Uses `random.Random(2026)`. Returns counts keyed `subscribers, packages, subscriptions, usage_events, transactions, cases, incidents, offers`.
- `seed_all.main()` prints `f"Seeded {n['subscribers']} subscribers, {n['packages']} packages, {n['transactions']} transactions, {n['cases']} cases, {n['incidents']} incidents, {n['offers']} offers."`

Seed content (all dates relative to `now`, local tz):

Packages (code · name · kind · data_mb · minutes · sms · days · ৳ · tag):
`D1-1D` 1 GB Daily · data · 1024 · 0 · 0 · 1 · 29 · — | `D3-3D` 3 GB Weekend · data · 3072 · 0 · 0 · 3 · 69 · WEEKEND | `D8-7D` 8 GB Weekly · data · 8192 · 0 · 0 · 7 · 149 · BEST VALUE | `D15-30D` 15 GB Monthly · data · 15360 · 0 · 0 · 30 · 349 · — | `D30-30D` 30 GB Monthly · data · 30720 · 0 · 0 · 30 · 549 · — | `D50-30D` 50 GB Monthly · data · 51200 · 0 · 0 · 30 · 749 · — | `V100-7D` 100 Minutes · voice · 0 · 100 · 0 · 7 · 79 · SHORT CALLS | `V300-30D` 300 Minutes · voice · 0 · 300 · 0 · 30 · 199 · VOICE | `V600-30D` 600 Minutes · voice · 0 · 600 · 0 · 30 · 349 · — | `B5-100` 5 GB + 100 min · bundle · 5120 · 100 · 0 · 7 · 179 · — | `B15-300` Smart 15 GB + 300 min · bundle · 15360 · 300 · 0 · 30 · 399 · POPULAR | `B20-200` 20 GB + 200 min · bundle · 20480 · 200 · 0 · 30 · 449 · EXCLUSIVE | `B40-500` 40 GB + 500 min · bundle · 40960 · 500 · 0 · 30 · 799 · — | `S100-30D` 100 SMS · sms · 0 · 0 · 100 · 30 · 29 · — | `S500-30D` 500 SMS · sms · 0 · 0 · 500 · 30 · 79 · —

Personas:

| msisdn | name | plan | district | balance / due | points | subscriptions | extras |
|---|---|---|---|---|---|---|---|
| 01712342841 | Samiha Khan | prepaid | Dhaka | ৳486.50 | 840 | `B15-300` 8602 MB / 182 min left, expires in 3 days, auto_renew off; `S100-30D` 74 SMS left | txns: recharge ৳200 bKash today success; recharge ৳100 Nagad 8 days ago success; recharge ৳300 bKash 12 days ago failed ("Payment timed out"); purchase `B15-300` yesterday; cases: TC-2048 "Recharge balance not updated" in_review, TC-1986 "Package activation confirmation" resolved |
| 01812347392 | Rafi Ahmed | prepaid | Chattogram | ৳42.00 | 120 | `D8-7D` 2100 MB left, expires in 5 days | txn: recharge ৳300 Nagad pending today |
| 01912345501 | Nusrat Mahmud | postpaid | Rajshahi | due ৳1240.00 | 300 | `B40-500` 30000 MB / 410 min, expires in 18 days | — |
| 01612341109 | Tanvir Hasan | prepaid | Sylhet | ৳215.00 | 60 | `D15-30D` 1200 MB left, expires in 11 days | case: "Slow mobile data" open |
| 01512346620 | Farhana Islam | prepaid | Gazipur | ৳730.25 | 2150 | `B20-200` 12000 MB / 150 min, expires in 20 days | cases: "Unexpected data deduction" open (high), "SIM replacement query" resolved |

Usage: 30 days per persona — daily data events (Samiha 150–350 MB/day, Rafi 300–600, Nusrat 600–1200, Tanvir 200–500, Farhana 250–450), 0–6 voice calls/day of 1–12 min, 0–3 SMS/day; charge 0 for all except 2–3 `vas` events per persona of ৳2.50–৳10 ("Caller tune renewal", "News alert subscription") so `explain_deductions` has content.

Incidents: Sylhet / "Sylhet Sadar" congestion investigating, started 2 hours ago, message "Some subscribers may experience slower data speeds during peak hours."; Gazipur / "Gazipur Sadar" maintenance scheduled, starts tomorrow 02:00 local, ends 03:30 local.

Offers: "20 GB + 200 min exclusive" (package `B20-200`, audience all); "1 GB bonus for 700 points" (`points_cost=700`, package = a 1 GB 3-day package `RW-1G-3D` created inactive so it is not sold, audience all); "10% cashback on ৳200+ recharge" (`cashback_percent=10`, `cashback_cap=30`, `min_recharge=200`, audience prepaid). All `ends_on = today + 60 days`.

- [ ] **Step 1: Write `tests/test_seed_telco.py`** (uses the rolled-back `db` fixture, so nothing persists; on an already-seeded DB `seed` returns zeros and the persona assertions still hold):

```python
def test_seed_is_idempotent(db):
    seed_telco.seed(db); again = seed_telco.seed(db)
    assert set(again.values()) == {0}

def test_samiha_matches_reference_ui(db):
    seed_telco.seed(db)
    s = db.query(Subscriber).filter_by(msisdn="01712342841").one()
    out = accounts.get_account_summary(db, s.id)
    assert out.main_balance == Decimal("486.50") and out.totals.data_left_mb == 8602
    assert out.totals.minutes_left == 182 and out.totals.sms_left == 74
    assert 2 <= (out.nearest_expiry - utc_now()).days <= 3

def test_sylhet_has_active_incident(db):
    seed_telco.seed(db)
    assert network.check_network_status(db, "Sylhet")
```
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `seed_telco.py`, wire `seed_all.main()`, update the README seed line.
- [ ] **Step 4:** Run the file → PASS. Then on the dev DB: `uv run python -m app.data.seed_all` → `Seeded 5 subscribers, 16 packages, ...` (15 sellable + the inactive reward pack); run it again → `Seeded 0 subscribers, ...`. Full suite → all pass.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(data): telco demo seed"`.

---

### Task 11: Phase verification

**Files:** none new.

- [ ] **Step 1:** Fresh DB check: `docker exec telco-pg psql -U telco -c "DROP DATABASE IF EXISTS telco_verify" -c "CREATE DATABASE telco_verify"`, then from `backend/`: `DATABASE_URL=postgresql+psycopg://telco:telco@localhost:5435/telco_verify uv run alembic upgrade head && DATABASE_URL=... uv run python -m app.data.seed_all` → Expected: migrations to `c1a7e0f3b9d2` and `Seeded 5 subscribers, ...`. Drop `telco_verify` afterwards.
- [ ] **Step 2:** Full suite on the dev DB → Expected: all pass, 0 failures.
- [ ] **Step 3:** Smoke-start: `uv run uvicorn app.main:app --port 8011` in the background, `curl -s localhost:8011/health` → `{"status":"ok"}`; stop it. `uv run python -c "import app.agent.worker, app.scheduler.worker"` → no output.
- [ ] **Step 4:** Leftover scan: `grep -rniE "propert(y|ies)|booking|viewing|listing|lead_status|cold.?call" app --include=*.py` → only hits in `app/agent/turn_router.py`, `turn_judge.py`, `quick_reply.py`, `prompt_defaults.py`, `services/voice_preview.py` (Phase 2 rewrites those prompts). Anything else gets removed.
- [ ] **Step 5: Commit** any fixes — `git commit -am "chore: phase 1 verification fixes"` (skip if nothing changed).
