# Telco Phase 4 — Admin Portal and Nudges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An operator logs in at `/login` and runs the demo from a telco. admin portal (control center, subscribers, transactions, support queue, network, AI monitor, offers, plus the kept chatbot/knowledge/conversations pages). They can stage a network incident or resolve a case live, and run proactive nudges that appear in the customer portal's notification bell. Clicking a notification opens the assistant, which greets with that nudge.

**Architecture:**
- Backend:
  - New `bss.notifications` (nudge rules, dedupe, portal reads) and `bss.ops` / `bss.monitor` (admin aggregates). Admin writes (case status, incidents, offers) go through `bss` with `Actor.admin` and an audit row.
  - New admin routes under `/api/admin/*`, all behind `get_current_admin`. New customer routes `/api/me/notifications*`.
  - The scheduler runs the nudge sweep every 15 minutes; `POST /api/admin/nudges/run` runs it on demand.
- Frontend:
  - The real-estate dashboard pages are deleted. The dashboard gets a telco. shell (same tokens as the portal) with Operations and Agent nav groups.
  - The portal topbar gets a notification bell. A click marks the notification read and starts a fresh assistant session carrying `nudge_id`.
  - The token route only lets an admin join an existing room by `room_name`.

**Tech Stack:**
- Backend: Python 3.11, FastAPI, SQLAlchemy 2 (sync), Alembic, APScheduler, pytest on real Postgres (`telco-pg`, port 5435), uv; LiveKit agents 1.7.
- Frontend: Next.js 15.5, React 19, Tailwind v4, livekit-client, @livekit/components-react, lucide-react, sonner, next-themes, pnpm.

**Spec:** `docs/superpowers/specs/2026-10-22-telco-agent-design.md` (sections 3.1–3.2, 6.1, 6.2, 6.5, 6.6, 7, 8; Phase 4 in section 9). Carry-overs: memory files `telco-phase1-carryovers.md`, `telco-phase2-carryovers.md`, `telco-phase3-carryovers.md`; each item folded in is named in its task. Reference UI: `C:\Users\BS23-DESKTOP-00038\Downloads\telco_dashboard.html` (admin mode: sections `page-admin-overview`, `page-subscribers`, `page-transactions`, `page-cases`, `page-network`, `page-ai-monitor`; its numbers are fictional, ours come from the DB).

## Global Constraints

- Backend commands run from `backend/`: `uv run pytest -q`, `uv run alembic check`. Frontend commands run from `frontend/`: `pnpm typecheck` and `pnpm lint`.
- Every `/api/admin/*` route depends on `get_current_admin`; a customer `portal_session` token gets 401. Every `/api/me/*` route stays customer-only.
- Admin writes use `Actor.admin` (audit) and `CaseSource.admin` where a case source applies; every admin write records one `audit_events` row via `bss.audit.record`.
- Nudge rules (spec 7), exact thresholds:
  - `pack_expiring`: active subscription, `expires_at` within 3 days of now, `auto_renew` false.
  - `low_balance`: prepaid subscriber, `main_balance` < ৳50.
  - `low_data`: active subscription whose package has `data_mb > 0` and `data_left_mb < 10%` of `package.data_mb`.
  - `case_update`: a case's status changed by an admin.
  - Only subscribers with `status = active` get nudges.
- Notification payload keys (agent `snapshot._NUDGE_TEXT` reads them): `pack_expiring {package_name, expires_at}`, `low_balance {balance}`, `low_data {package_name, data_left_mb}`, `case_update {case_ref, status}`. `expires_at` is ISO-8601; numbers are JSON numbers.
- Notification `subject_key` (the dedupe key with subscriber and kind): `pack_expiring` → subscription id; `low_data` → subscription id; `low_balance` → local date `YYYY-MM-DD` (`bss.clock.local_tz`); `case_update` → `f"{case_ref}:{status}"`. Inserts use `INSERT … ON CONFLICT DO NOTHING` on `uq_notification_subject`, so concurrent sweeps never error.
- Scheduler: nudge sweep every 15 minutes, `max_instances=1`, `coalesce=True`.
- `nudge_id` reaches the agent only as a UUID in dispatch metadata (`buildDispatchMetadata` already validates it); the agent already ignores a nudge that is not the session subscriber's (`snapshot._nudge_text`).
- MSISDNs are masked (`bss.accounts.mask_msisdn`) in every admin list and detail view.
- Money JSON is numbers (reuse the `_json` approach in `routes_me.py`); shown as `৳ 486.50` / `৳ 1,240`. Times shown in `Settings.agency_timezone`.
- Look: the Phase 3 tokens in `frontend/styles/globals.css` (indigo `#4f46e5`, mint `#20b89a`, orange `#ff9b55`, red `#e45b73`, panel radius 17px, Inter, breakpoints `tablet:` ≤1100, `phone:` ≤760, `narrow:` ≤390). No new hard-coded hex colours.
- Every frontend task invokes the `frontend-design` and `ui-ux-pro-max` skills before editing (and `dataviz` where it draws a chart), and ends with `pnpm typecheck` and `pnpm lint` passing.
- `.env` / `.env.local` are never committed.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Out of scope

Real-microphone voice testing (a demo-prep step, listed in the README checklist), the confirm card keeping earlier receipts, a partly typed code surviving "Open full view", portal writes refreshing an open agent session's snapshot, the agent's cut-off replies investigation, `bss_world` cleanup concurrency, and `app/services/taka.py` (still used by speech formatting, so not a leftover).

## Review Focus

1. **Cross-role access to the new routes.** A customer cookie on any `/api/admin/*` route gets 401; an anonymous request gets 401; an admin cookie on `/api/me/notifications` gets 401. → Task 2 test `test_admin_routes_refuse_customer_and_anon` (parametrised over every admin GET) and Task 1 test `test_notifications_need_customer`.
2. **Sweep runs twice, or the scheduler and "Run nudges now" overlap.** Expected: one notification per (subscriber, kind, subject_key), no error. → Task 1 tests `test_sweep_is_idempotent` and `test_notify_conflict_is_silent`.
3. **Marking someone else's notification read.** `POST /api/me/notifications/{other_subscriber_notification_id}/read` → 404, the row stays unread. → Task 1 test `test_cannot_read_other_subscribers_notification`.
4. **Joining an existing room without an admin session.** `POST /api/token {room_name: "<any>"}` with no admin `session` cookie → 403, no token. → Task 7 Step 5 manual curl check.
5. **Repeated or invalid admin writes.** PATCH a case to its current status → 200, no second `case_update`; resolve an already-resolved incident → 200 unchanged; create an incident with `ends_at` before `starts_at` → 422; delete an offer that has transactions → 409. → Task 3 tests `test_same_status_does_not_renotify`, `test_resolve_twice_is_noop`, `test_incident_end_before_start_422`; Task 5 test `test_delete_offer_in_use_409`.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/bss/notifications.py` (create) | `notify`, `run_sweep`, `list_for`, `mark_read`, `mark_all_read`, `describe` |
| `backend/app/bss/ops.py` (create) | admin aggregates: overview, subscriber directory/detail, transaction list/stats, case queue/stats, district health |
| `backend/app/bss/monitor.py` (create) | AI monitor metrics from `conversations`, `conversation_messages`, `audit_events` |
| `backend/app/bss/cases.py`, `network.py`, `rewards.py`, `otp.py` (modify) | `set_case_status`, incident create/resolve, `specific` audience, atomic throttle |
| `backend/app/api/routes_admin.py` (create) | `/api/admin/*` reads + writes |
| `backend/app/api/schemas_admin.py` (create) | admin request/response models |
| `backend/app/api/routes_me.py`, `schemas_me.py` (modify) | `/api/me/notifications*` |
| `backend/app/scheduler/jobs.py`, `worker.py` (modify) | `run_nudges` job every 15 min |
| `backend/alembic/versions/*` (create) | offer audience `specific` + `offer_subscribers`; `audit_events` FK `SET NULL` |
| `frontend/app/dashboard/{bookings,leads,properties,schedule,incoming}/**`, `components/dashboard/properties/**`, `components/app/scheduled-call-watcher.tsx`, `components/dashboard/knowledge/properties-sync-card.tsx`, `lib/types/{booking,property,schedule}.ts` (delete) | real-estate leftovers |
| `frontend/components/dashboard/shell/*` (create), `app/dashboard/layout.tsx` (modify) | telco. admin shell |
| `frontend/lib/admin-api.ts`, `lib/types/admin.ts`, `lib/admin-query.ts` (create) | typed `/api/admin` client and query hook |
| `frontend/app/dashboard/{page,subscribers,transactions,cases,network,ai-monitor}/**`, `components/dashboard/{control,subscribers,transactions,cases,network,monitor}/*` (create/replace) | admin pages |
| `frontend/components/dashboard/offers/*`, `lib/types/offer.ts` (rewrite) | reshaped offers |
| `frontend/components/portal/shell/notification-bell.tsx` (create), `components/chat-bubble/chat-bubble-context.tsx`, `app/api/token/route.ts` (modify) | bell, nudge sessions, room gating |

---

### Task 1: Notifications — nudge sweep, scheduler job, portal API

Carry-overs: phase 1 "no bss.notifications yet"; phase 2 nudge payload keys.

**Files:**
- Create: `backend/app/bss/notifications.py`, `backend/tests/test_notifications.py`
- Modify: `backend/app/bss/types.py`, `backend/app/api/routes_me.py`, `backend/app/api/schemas_me.py`, `backend/app/scheduler/jobs.py`, `backend/app/scheduler/worker.py`

**Interfaces:**
- Produces (`app.bss.notifications`):
  - `notify(db, subscriber_id: UUID, kind: NotificationKind, subject_key: str, payload: dict) -> bool` — `INSERT … ON CONFLICT ON CONSTRAINT uq_notification_subject DO NOTHING`; returns True when a row was inserted. Caller commits.
  - `run_sweep(db, *, now: datetime | None = None) -> dict[str, int]` — applies the three rule-based kinds (Global Constraints), commits, returns new-row counts keyed by kind value (all three keys present, `case_update` is not swept).
  - `NotificationView(_Base)` in `bss/types.py`: `id: UUID, kind: NotificationKind, title: str, body: str, payload: dict, created_at: datetime, read_at: datetime | None`.
  - `describe(row: Notification) -> tuple[str, str]` — title/body in English, e.g. `("Pack expiring", "Your 15 GB + 300 min pack expires on 26 Oct.")`, `("Low balance", "Your balance is ৳ 32.00.")`, `("Data running low", "Only 820 MB left on <pack>.")`, `("Case update", "TC-2048 is now resolved.")`. Use `app.agent.telco_format` / `speech_numbers` formatters only if they have no LiveKit import; otherwise format locally.
  - `list_for(db, subscriber_id, *, limit=20) -> tuple[int, list[NotificationView]]` — unread count and newest first.
  - `mark_read(db, subscriber_id, notification_id) -> NotificationView` — raises `NotificationNotFound` (new `BssError`, code `notification_not_found`, mapped to 404 in `bss_http.py`) when missing or another subscriber's. Idempotent.
  - `mark_all_read(db, subscriber_id) -> int`.
- Routes (customer, `no-store`): `GET /api/me/notifications` → `{unread: int, items: NotificationView[]}`; `POST /api/me/notifications/{id}/read` → `NotificationView`; `POST /api/me/notifications/read-all` → `{updated: int}`.
- Scheduler: `jobs.run_nudges()` (async, `asyncio.to_thread`, logs counts when any > 0, swallows+logs exceptions); `worker.py` adds it every 15 minutes and updates the startup log line.

- [ ] **Step 1: Write failing tests** in `tests/test_notifications.py` (use `bss_world` builders and `customer_api`):

```python
def test_pack_expiring_fires_within_3_days_without_auto_renew(db, bss_world): ...
    # sub with active subscription expiring now+2d, auto_renew False -> counts["pack_expiring"] == 1
    # payload == {"package_name": pkg.name, "expires_at": <iso>}; subject_key == str(subscription.id)
def test_pack_expiring_skips_auto_renew_and_far_expiry(db, bss_world): ...  # auto_renew True, or now+4d -> 0
def test_low_balance_prepaid_only(db, bss_world): ...  # prepaid 49.99 -> 1 (payload balance 49.99); postpaid 10 -> 0; prepaid 50 -> 0
def test_low_data_under_10_percent(db, bss_world): ...  # 10240 MB pack, 1000 left -> 1; 1100 left -> 0; voice-only pack (data_mb 0) -> 0
def test_suspended_subscriber_gets_none(db, bss_world): ...
def test_sweep_is_idempotent(db, bss_world): ...  # run twice -> second run all zeros; one row per subject
def test_notify_conflict_is_silent(db, bss_world): ...  # notify(...) twice same key -> True then False, no exception
def test_list_and_mark_read(bss_world, customer_api): ...
    # GET -> unread 2; POST /{id}/read -> read_at set; GET -> unread 1; read-all -> {"updated": 1}
def test_cannot_read_other_subscribers_notification(bss_world, customer_api): ...  # 404, row still unread
def test_notifications_need_customer(api, anon_api): ...  # admin cookie and anon -> 401 on all three routes
```

- [ ] **Step 2: Run** `uv run pytest tests/test_notifications.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the module, routes and scheduler job.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Seed check:** `uv run python -m app.data.seed_all --reset`, then `uv run python -c "from app.db.session import SessionLocal; from app.bss import notifications as n; print(n.run_sweep(SessionLocal()))"`. Expected: `pack_expiring` ≥ 1 (Samiha), `low_balance` ≥ 1 (Rafi), `low_data` ≥ 1 (Tanvir). If a persona does not trigger, adjust `seed_telco.py` (Samiha's pack `auto_renew=False`, Tanvir's data under 10%) and re-run.
- [ ] **Step 6: Commit** `feat(bss): notifications, nudge sweep and portal notification API`.

### Task 2: Admin read API — control center, subscribers, transactions

Carry-over: phase 1 "DashboardSummary lost leads/bookings fields" (replaced by the overview below).

**Files:**
- Create: `backend/app/bss/ops.py`, `backend/app/bss/monitor.py`, `backend/app/api/routes_admin.py`, `backend/app/api/schemas_admin.py`, `backend/tests/test_admin_reads.py`, `backend/tests/test_monitor.py`
- Modify: `backend/app/main.py`, `backend/tests/conftest.py` (only if a helper to seed conversations/messages is needed)

**Interfaces:**
- `routes_admin.router = APIRouter(prefix="/api/admin", dependencies=[Depends(get_current_admin)])`, responses `no-store`, Decimals as numbers.
- `bss.monitor`:
  - `TOOL_INTENT: dict[str, str]` mapping every agent tool name to one of `"Balance & usage"` (`get_account_summary`, `get_usage_breakdown`, `explain_deductions`), `"Packages"` (`search_packages`, `recommend_packages`, `purchase_package`), `"Recharge"` (`start_recharge`, `lookup_transactions`), `"Offers & rewards"` (`get_offers_and_points`, `redeem_reward`), `"Support"` (`create_support_case`, `get_case_status`, `request_human_agent`), `"Network"` (`check_network_status`), `"Knowledge base"` (`search_knowledge_base`); anything else (`verify_otp`, `cancel_pending_action`, unknown) → not counted as an intent.
  - `metrics(db, *, since: datetime) -> MonitorMetrics`: `chats` (conversations started since), `turns` (user messages since), `fallback_rate` (share of user turns with no `role="tool"` row before the next user message in that conversation; 0.0 when no turns), `resolution_rate` (share of chats without a `request_human_agent` tool row; 0.0 when no chats), `median_first_response_s` and `p95_first_response_s` (per user turn: seconds to the next `role="assistant"` message; `None` when no samples), `intents: list[{label, count, share}]` sorted desc.
  - `review_queue(db, *, since, limit=5) -> list[{conversation_id, started_at, subscriber_name, no_tool_turns, preview}]` — conversations with ≥ 2 no-tool turns, newest first.
  - `audit_trail(db, *, limit=50) -> list[{created_at, actor, action, subscriber_name, msisdn_masked, detail}]` newest first.
- `bss.ops` + routes:
  - `GET /api/admin/overview` → `{subscribers: {total, prepaid, postpaid}, recharge_today: {amount, count}, cases: {open, high_open}, ai: {chats_24h, resolution_rate}, activity: [{date, recharge_amount, cases_created}] (7 local days, oldest first, zero-filled), health: {recharge_success_rate_24h (success/(success+failed), None when none), median_first_response_s, active_incidents, pending_transactions}, attention: [{kind, title, detail, severity: "high"|"review"|"investigate", href}]}`. Attention rules: pending transactions > 0 → `/dashboard/transactions?status=pending`; high-priority open cases older than 2 h → `/dashboard/cases?priority=high`; fallback rate over the last 24 h > 0.08 with ≥ 10 turns → `/dashboard/ai-monitor`; each active outage/congestion → `/dashboard/network`. "Today" is the local day (`bss.clock.local_day_bounds`).
  - `GET /api/admin/subscribers?q=&plan_type=&status=&limit=25&offset=0` → `{items: [{id, full_name, msisdn_masked, plan_type, district, status, main_balance, postpaid_due, joined_on}], total}`. `q` matches name (ILIKE) or msisdn digits (contains). `limit` ≤ 100.
  - `GET /api/admin/subscribers/{id}` → `{subscriber (list item shape + reward_points, preferred_language), summary: AccountSummary, transactions: TransactionView[10], cases: CaseView[10], notifications: NotificationView[10]}`; 404 when unknown.
  - `GET /api/admin/transactions?status=&type=&q=&days=7&limit=25&offset=0` → `{items: [TransactionView + subscriber_name, msisdn_masked], total}`; `q` matches ref or msisdn digits; `days` ≤ 90.
  - `GET /api/admin/transactions/stats` → today: `{volume (success amount sum), attempts, success, pending, failed, success_rate}`.
  - `GET /api/admin/ai-monitor?window=24h|7d` → `{metrics, review_queue, audit_trail}`.

- [ ] **Step 1: Write failing tests.** `tests/test_monitor.py` builds conversations/messages directly:

```python
def test_fallback_rate_counts_turns_without_tools(db): ...  # 4 user turns, tools after 3 -> 0.25
def test_first_response_median_and_p95(db): ...  # gaps 1,2,3,10 s -> median 2.5, p95 >= 3 and <= 10
def test_resolution_rate_excludes_handoffs(db): ...  # 4 chats, 1 with request_human_agent -> 0.75
def test_intents_group_tools(db): ...  # get_account_summary x2 + get_usage_breakdown x1 -> "Balance & usage" count 3; verify_otp not an intent
def test_empty_window_has_no_samples(db): ...  # metrics on a future `since` -> chats 0, rates 0.0, latency None
```

`tests/test_admin_reads.py`:

```python
def test_admin_routes_refuse_customer_and_anon(customer_api, anon_api, bss_world): ...
    # parametrise over every GET path in routes_admin -> 401 for both
def test_overview_counts_today_and_zero_fills(api, bss_world): ...  # 7 activity points; a success recharge today is in recharge_today
def test_subscriber_search_masks_msisdn(api, bss_world): ...  # q=<last 4 digits> finds it; no item contains the full msisdn
def test_subscriber_detail_404(api): ...
def test_transactions_filters_and_stats(api, bss_world): ...  # status=pending returns only pending; stats.success_rate == success/(success+failed)
def test_attention_lists_pending_transactions(api, bss_world): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_monitor.py tests/test_admin_reads.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `bss.monitor`, `bss.ops`, schemas and routes; register the router in `main.py`. Percentiles: nearest-rank on sorted samples.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(api): admin control center, subscriber, transaction and AI monitor reads`.

### Task 3: Admin writes — support queue and network incidents

**Files:**
- Modify: `backend/app/bss/cases.py`, `backend/app/bss/network.py`, `backend/app/bss/ops.py`, `backend/app/api/routes_admin.py`, `backend/app/api/schemas_admin.py`
- Create: `backend/tests/test_admin_writes.py`

**Interfaces:**
- `bss.cases.set_case_status(db, ref: str, status: CaseStatus, *, actor: Actor = Actor.admin) -> CaseView` — normalises `ref`; `CaseNotFound` when unknown. When the status changes: sets `resolved_at` (now) on `resolved`, clears it otherwise; records audit `action="case_status"`, `detail={"ref", "from", "to"}`; calls `notifications.notify(kind=case_update, subject_key=f"{ref}:{status}", payload={"case_ref": ref, "status": status.value})`; commits. Same status → returns the view, writes nothing.
- `bss.network.create_incident(db, *, district, area, kind, status, message, starts_at=None, ends_at=None) -> IncidentAdminView` — `status` is `investigating` or `scheduled` (else `InvalidRequest`); `starts_at` defaults to now; `ends_at` must be after `starts_at` (else `InvalidRequest` → 422); audit `incident_create`, `subscriber_id=None`.
- `bss.network.resolve_incident(db, incident_id: UUID) -> IncidentAdminView` — sets `status=resolved` and `ends_at=now` when `ends_at` is null or in the future; already resolved → unchanged; unknown → `IncidentNotFound` (new `BssError`, `incident_not_found`, 404). Audit `incident_resolve`.
- `IncidentAdminView` = `IncidentView` + `id: UUID`, `active: bool` (matches `active_incidents_query` semantics).
- Routes:
  - `GET /api/admin/cases?status=&priority=&limit=25&offset=0` → `{items: [CaseView + subscriber_name, msisdn_masked], total}`, ordered high priority first, then oldest open first.
  - `GET /api/admin/cases/stats` → `{open (open + in_review), high_open, avg_resolution_hours_7d (None when none), ai_assisted_share_7d (source=agent share of cases created in 7 d)}`.
  - `PATCH /api/admin/cases/{ref} {status}` → `CaseView`.
  - `GET /api/admin/network` → `{districts: [{district, health: "normal"|"degraded"|"maintenance", incidents: int}], incidents: IncidentAdminView[]}`. Districts are the union of subscriber and incident districts, sorted; `degraded` when an active outage/congestion, else `maintenance` when an active or future scheduled maintenance. `incidents` lists active and future ones first, then resolved from the last 7 days.
  - `POST /api/admin/network/incidents` → `201 IncidentAdminView`; `POST /api/admin/network/incidents/{id}/resolve` → `IncidentAdminView`.

- [ ] **Step 1: Write failing tests** in `tests/test_admin_writes.py`:

```python
def test_resolve_case_sets_resolved_at_and_notifies(api, db, bss_world): ...
    # PATCH TC-x {status: resolved} -> resolved_at set; one case_update notification with payload {"case_ref", "status": "resolved"}; one audit row actor admin
def test_same_status_does_not_renotify(api, db, bss_world): ...  # PATCH resolved twice -> still one notification, one audit row
def test_reopen_clears_resolved_at(api, bss_world): ...
def test_case_ref_normalised_and_unknown_404(api, bss_world): ...  # "tc 2048" works; "TC-1" -> 404
def test_create_incident_is_seen_by_agent_query(api, db, bss_world): ...
    # POST outage in a district -> bss.network.check_network_status for a sub in that district lists it
def test_incident_end_before_start_422(api): ...
def test_resolve_twice_is_noop(api, db): ...  # second call 200, ends_at unchanged
def test_district_health(api, db, bss_world): ...  # congestion -> degraded; future maintenance -> maintenance
```

- [ ] **Step 2: Run** `uv run pytest tests/test_admin_writes.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(api): admin case status and network incident staging`.

### Task 4: Nudges on demand and backend hardening carry-overs

Carry-overs: phase 1 "audit OTP issue/verify and target-credit events", "audit_events cascade on subscriber delete"; phase 3 "move throttle constants into bss.otp, atomic check", "otp.verify counts attempts without a row lock", "TransactionView has no points field", "`GET /api/me/cases` drops newer resolved cases"; phase 2 R7 test isolation.

**Files:**
- Modify: `backend/app/api/routes_admin.py`, `backend/app/bss/otp.py`, `backend/app/bss/types.py`, `backend/app/bss/transactions.py`, `backend/app/bss/recharge.py`, `backend/app/api/routes_me.py`, `backend/app/api/routes_me_actions.py`, `backend/app/agent/actions.py`, `backend/app/models/telco.py`, `backend/tests/test_embedding_jobs.py` (R7 only)
- Create: Alembic migration `audit_events_subscriber_set_null`; tests in `backend/tests/test_hardening.py`

**Interfaces:**
- `POST /api/admin/nudges/run` → `{created: {pack_expiring, low_balance, low_data}}`; audit `action="nudges_run"`, `subscriber_id=None`.
- `bss.otp`:
  - `MAX_CODES_PER_WINDOW = 5`, `CODE_WINDOW = timedelta(minutes=15)` move here; `agent/actions.py` and `routes_me_actions.py` import them (no local copies).
  - `issue(...)` gains keyword `throttle: bool = False`. With `throttle=True` it locks the subscriber row (`SELECT … FOR UPDATE` on `subscribers`), counts `issued_since(now - CODE_WINDOW)`, and raises `LimitExceeded(code="too_many_codes")` (or a new `TooManyCodes` `BssError` mapped to 429 — implementer's choice, the portal response body must stay `{"code": "too_many_codes"}` with 429) before inserting. The portal start route uses `throttle=True` and drops its own check. The agent keeps its in-session list as-is.
  - `verify(...)` loads the challenge `with_for_update()`.
  - `issue` and `verify` record audit rows `otp_issue` / `otp_verify` with `detail={"purpose", "ok"}` (never the code).
- Recharge to another number records a second audit row `action="target_credit"` with `subscriber_id` of the target when that msisdn is a subscriber (else `None`) and `detail={"ref", "amount", "from_masked"}`.
- `TransactionView.points_spent: int | None` — for `redeem` transactions, the offer's `points_cost`; else `None`. Frontend portal recent-activity redeem row shows `"{n} pts"` (update `frontend/components/portal/balance/*` or wherever the "Points" label is rendered; `lib/types/portal.ts` gains the field).
- `GET /api/me/cases`: order by `created_at` desc across all statuses, limit 20 (fix the open-first-then-resort bug).
- Migration: `audit_events.subscriber_id` FK `ondelete="SET NULL"` (model `_subscriber_fk(nullable=True, ondelete …)` — adapt the helper or pass a dedicated `mapped_column`). `uv run alembic check` clean.
- R7: make `test_embedding_jobs`'s migration test run without skipping on a seeded dev DB by giving it its own throwaway schema/DB or Chroma collection; if that takes more than a small fixture change, leave the skip and record why in the report.

- [ ] **Step 1: Write failing tests** in `tests/test_hardening.py`:

```python
def test_run_nudges_endpoint(api, bss_world): ...  # 200 with three counts; second call all zero
def test_portal_throttle_sixth_code_429(bss_world, customer_api): ...  # 5 starts ok, 6th -> 429 {"code": "too_many_codes"}
def test_otp_issue_and_verify_are_audited_without_code(db, bss_world): ...  # audit rows exist; no detail value equals the code
def test_target_credit_audit(db, bss_world): ...  # A recharges B -> audit row target_credit with subscriber_id == B.id
def test_redeem_transaction_has_points_spent(db, bss_world): ...
def test_me_cases_newest_first_across_statuses(bss_world, customer_api): ...  # 21 open old + 1 resolved new -> resolved new is first
def test_deleting_subscriber_keeps_audit_rows(db, bss_world): ...  # audit row survives with subscriber_id None
```

- [ ] **Step 2: Run** `uv run pytest tests/test_hardening.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, including the migration (`uv run alembic revision -m "audit_events subscriber set null"`, hand-edit), then `uv run alembic upgrade head`.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run alembic check`. Expected: all pass, "No new upgrade operations detected".
- [ ] **Step 5: Commit** `fix(bss): atomic OTP throttle, OTP and credit audit, points on redeem rows, run-nudges endpoint`.

### Task 5: Offers admin API with specific-subscriber audience

Carry-over: phase 1 "OfferAudience lacks specific subscribers (spec 3.2)".

**Files:**
- Modify: `backend/app/models/telco.py`, `backend/app/bss/rewards.py`, `backend/app/api/routes_admin.py`, `backend/app/api/schemas_admin.py`
- Create: Alembic migration `offer_audience_specific`; `backend/tests/test_admin_offers.py`

**Interfaces:**
- Model: `OfferAudience.specific = "specific"`; table `offer_subscribers (offer_id FK offers CASCADE, subscriber_id FK subscribers CASCADE, PK both)`; `Offer.subscribers` relationship. Migration adds the enum value with `op.execute("ALTER TYPE offer_audience ADD VALUE IF NOT EXISTS 'specific'")` inside `with op.get_context().autocommit_block():`.
- `bss.rewards._eligible`: `specific` offers are eligible only for listed subscribers.
- Offer kinds (derived, not stored): `points` (`points_cost` + `package_id`), `cashback` (`cashback_percent` + `min_recharge`, optional `cashback_cap`), `pack` (`package_id` only). Validation (422 `invalid_request`): exactly one kind's fields set; `cashback_percent` 0 < p ≤ 100; `points_cost` > 0; `ends_on` ≥ `starts_on`; `audience=specific` needs ≥ 1 known `subscriber_ids`, other audiences ignore them.
- Routes: `GET /api/admin/offers` → `AdminOffer[]` (`id, title, description, terms, kind, package_id, package_name, points_cost, cashback_percent, cashback_cap, min_recharge, audience, subscriber_ids, subscribers: [{id, full_name, msisdn_masked}], starts_on, ends_on, is_active, redemptions (transaction count)`); `POST` → 201; `PATCH /{id}` (partial, re-validated as a whole); `DELETE /{id}` → 204, or 409 `offer_in_use` when transactions reference it. All writes audited (`offer_create|offer_update|offer_delete`).
- `GET /api/admin/packages` → active `PackageView[]` (for the offer form's package select).

- [ ] **Step 1: Write failing tests** in `tests/test_admin_offers.py`:

```python
def test_create_each_kind(api, bss_world): ...  # points, cashback, pack -> 201, kind echoed
def test_rejects_mixed_or_empty_kind(api, bss_world): ...  # points_cost + cashback_percent -> 422; none -> 422
def test_specific_audience_eligibility(api, db, bss_world): ...
    # specific offer for A -> in bss.rewards.get_offers_and_points(A) offers, not in B's
def test_specific_needs_subscribers(api): ...  # 422
def test_patch_revalidates(api, bss_world): ...
def test_delete_offer_in_use_409(api, db, bss_world): ...  # redeem txn referencing it -> 409; unused -> 204
```

- [ ] **Step 2: Run** `uv run pytest tests/test_admin_offers.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, migrate (`uv run alembic upgrade head`).
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run alembic check`. Expected: all pass, clean.
- [ ] **Step 5: Commit** `feat(api): admin offers with specific-subscriber audience`.

### Task 6: Agent carry-over fixes

Carry-overs (phase 2): `request_human_agent` not idempotent; `pending_case` never cleared; ActionRpc speaks twice on replay / silent on non-Bss failure; `limit_exceeded` text mixes recharge limits and code throttle; "recharge recharge" in transaction text; README intro "Outbound" bullet.

**Files:**
- Modify: `backend/app/agent/tools/support.py`, `backend/app/agent/userdata.py`, `backend/app/agent/action_rpc.py`, `backend/app/agent/tools/_common.py` (or wherever error → speech text lives), `backend/app/agent/tools/recharge.py` / `transactions` formatting, `README.md`
- Test: extend the existing agent tool tests (`backend/tests/test_*tools*.py`, fake `userdata`)

**Interfaces / decisions:**
- `request_human_agent` uses one `action_id` per session (`userdata.handoff_action_id`, created on first call), so a repeat call returns the same case ref.
- `pending_case` is set to `None` after a case is created (and on cancel), so quick replies work again afterwards.
- ActionRpc: a replayed confirm (same `action_id`, already done) returns `{ok: true}` without generating speech again; a non-`BssError` exception returns `{ok: false, error: "internal"}` and the agent says one short apology line.
- Error text: `LimitExceeded` from recharge amount/day limits and the code throttle get separate lines (throttle: "Too many codes were requested. Please wait a few minutes and try again." / recharge: the existing limits line). Match the existing language handling for Bangla.
- Transaction descriptions never repeat the type word (e.g. "recharge of ৳ 200", not "recharge recharge").
- README intro: remove the "Outbound" bullet.

- [ ] **Step 1: Write failing tests**, one per decision above (`test_handoff_is_idempotent_per_session`, `test_pending_case_cleared_after_create`, `test_rpc_replay_does_not_speak`, `test_rpc_internal_error`, `test_throttle_text_differs_from_limit_text`, `test_transaction_text_no_repeated_type`).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `fix(agent): idempotent handoff, case draft reset, RPC replay and error wording`.

### Task 7: Frontend admin foundation — cleanup, shell, data layer, room gating

Carry-overs: phase 1 "dashboard pages broken", "conversations API returns subscriber_id/subscriber_name"; phase 3 "gate room_name behind admin session cookie".

**Files:**
- Delete: `frontend/app/dashboard/{bookings,leads,properties,schedule,incoming}/**`, `frontend/components/dashboard/properties/**`, `frontend/components/app/scheduled-call-watcher.tsx`, `frontend/components/dashboard/knowledge/properties-sync-card.tsx`, `frontend/lib/types/{booking,property,schedule}.ts`, the matching parts of `frontend/lib/api-client.ts`, `lib/types/dashboard.ts` and `lib/types/public.ts`, and the real-estate tones in `components/dashboard/status-tones.ts`. Remove every import of them (`knowledge-view.tsx`, `source-table.tsx`, `overview-view.tsx`).
- Create: `frontend/components/dashboard/shell/{sidebar,topbar,mobile-drawer,nav-items}.tsx`, `frontend/lib/admin-api.ts`, `frontend/lib/types/admin.ts`, `frontend/lib/admin-query.ts`, placeholder pages `app/dashboard/{subscribers,transactions,cases,network,ai-monitor}/page.tsx`
- Modify: `frontend/app/dashboard/layout.tsx`, `frontend/app/api/token/route.ts`, `frontend/components/dashboard/conversations/*`, `frontend/components/dashboard/nav-items.ts` (delete after moving into `shell/nav-items.tsx`), old `components/dashboard/{sidebar,topbar}.tsx` (delete when replaced)

**Interfaces:**
- `lib/admin-query.ts`: `useAdminQuery<T>(key: AdminKey, fetcher: () => Promise<T>, deps?: unknown[]): {data?, error?, loading, reload}` and `invalidateAdmin(keys?: AdminKey[])` — same pattern as `lib/portal-sync.ts` (keep previous data while refetching); a 401 sends the browser to `/login`. `AdminKey = 'overview'|'subscribers'|'subscriber'|'transactions'|'txnStats'|'cases'|'caseStats'|'network'|'monitor'|'offers'|'packages'`. Reuse `portal-sync.ts` internals if the generalisation is a small change; otherwise mirror it.
- `lib/admin-api.ts`: one typed function per Task 2/3/4/5 route; types in `lib/types/admin.ts` mirror the backend models (Decimals are `number`).
- Shell (reference `nav-group#adminNav`, same look as the portal shell): sidebar 244px with brand, a Customer/Admin mode switch (Customer → `/`, Admin active), groups:
  - `OPERATIONS`: Control center `/dashboard` (LayoutDashboard), Subscribers `/dashboard/subscribers` (Users), Transactions `/dashboard/transactions` (ArrowUpRight), Support queue `/dashboard/cases` (LifeBuoy, badge = `caseStats.open`), Network status `/dashboard/network` (RadioTower), AI monitor `/dashboard/ai-monitor` (Sparkles).
  - `AGENT`: Chatbot, Knowledge base, Conversations, Offers (existing routes).
  - Hidden route label: `/dashboard/listen` → "Listen in".
  - Topbar: eyebrow "Operations", page title, theme toggle, admin menu (username, Log out → existing admin logout, then `/login`). ≤760px: off-canvas drawer.
- Conversations list/detail show `subscriber_name ?? 'Guest'`, link to `/dashboard/subscribers?id={subscriber_id}` when set; all lead/booking copy and the `client_id` filter are removed (filter by `subscriber_id` instead if the API supports it; otherwise drop the filter).
- Token route: when `room_name` is present, verify the admin `session` cookie by calling FastAPI `GET /api/auth/me` server-side (same pattern as `resolveSubscriberId`); not 200 → `403` and no token.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2: Implement** cleanup, shell, data layer, conversations fixes, token gating.
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`. Expected: no errors; `grep -rniE "propert(y|ies)|booking|lead" frontend/{app,components,lib} --include=*.ts*` finds only unrelated words (e.g. CSS `property`).
- [ ] **Step 4: Manual check:** every sidebar link resolves; Customer switch goes to `/`; `/dashboard/listen` still loads; dark/light readable; 760px drawer with no horizontal scroll.
- [ ] **Step 5: Manual check (Review Focus 4):** `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:3000/api/token -H 'content-type: application/json' -d '{"room_name":"x"}'` → `403`; the listen page as a logged-in admin still joins.
- [ ] **Step 6: Commit** `feat(web): telco admin shell, admin data layer and room join gating`.

### Task 8: Control center and Subscribers pages

**Files:**
- Create/replace: `frontend/app/dashboard/page.tsx`, `frontend/components/dashboard/control/*`, `frontend/app/dashboard/subscribers/page.tsx`, `frontend/components/dashboard/subscribers/*`
- Delete: `frontend/components/dashboard/overview/*` once unused (keep `kb-status-panel.tsx` if reused)

**Interfaces / content (reference `page-admin-overview`, `page-subscribers`):**
- Control center:
  - Hero "Operations control center" + status line ("All systems operational" when no attention item has severity `high`, else "Needs attention").
  - 4 metric tiles: Total subscribers (prepaid · postpaid), Recharge volume today (৳, count), Support cases (open, high), AI resolution rate (chats 24h).
  - "Service activity — last 7 days" chart: recharge ৳ and cases created per day (use `dataviz`; two series, labelled axes).
  - "Platform health" list: recharge success rate 24h, median first response, active incidents, pending transactions (show "—" for `None`).
  - "Needs attention" list from `overview.attention`, each linking to its `href`; empty state "Nothing needs attention right now."
  - A "Run nudges now" button → `POST /api/admin/nudges/run`, toast "Created N notifications" (N = sum) or "No new notifications".
  - The existing knowledge-base status panel stays below if it fits the layout.
- Subscribers: search box (debounced 300 ms) + plan/status filters, table (avatar initials, name, masked MSISDN, plan, balance or "৳ x due", status chip, joined), pagination (25). "View" opens a side sheet with `GET /subscribers/{id}`: summary tiles, recent transactions, cases, notifications. `?id=` in the URL opens the sheet directly (used by Conversations links). Tablet/phone: the table becomes stacked cards.

- [ ] **Step 1:** Invoke `frontend-design`, `ui-ux-pro-max`, `dataviz`.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`. Expected: no errors.
- [ ] **Step 4: Manual check** against a seeded DB: tiles match DB counts; search "2841" finds Samiha; sheet opens from `?id=`; Run nudges creates notifications once, then reports none.
- [ ] **Step 5: Commit** `feat(web): admin control center and subscriber directory`.

### Task 9: Transactions and Support queue pages

**Files:**
- Create: `frontend/app/dashboard/transactions/page.tsx`, `frontend/components/dashboard/transactions/*`, `frontend/app/dashboard/cases/page.tsx`, `frontend/components/dashboard/cases/*`

**Interfaces / content (reference `page-transactions`, `page-cases`):**
- Transactions: 4 tiles from `/transactions/stats` (Today's volume, Successful + rate, Pending, Failed); status segmented filter (All / Success / Pending / Failed, synced to `?status=`), type filter, search (ref or number); table: ref, subscriber (name + masked), type, channel, amount, time, status chip, failure reason on hover/expand for failed rows.
- Support queue: tiles from `/cases/stats` (Open cases + high, Avg. resolution 7 d, AI assisted share); filters All / High priority / Open (synced to `?priority=` / `?status=`); Refresh button; table: ref, subscriber, issue (category label + description excerpt), priority chip, age (from `created_at`), status chip, actions "Start review" (open → in_review) and "Resolve ✓" (→ resolved), "Reopen" on resolved. A status change calls PATCH, toasts, and `invalidateAdmin(['cases','caseStats','overview'])`.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`. Expected: no errors.
- [ ] **Step 4: Manual check:** resolving Farhana's open case shows a "Case update" notification in her portal bell after Task 11 (until then: one `case_update` row in the DB); filters survive reload via the URL.
- [ ] **Step 5: Commit** `feat(web): admin transactions and support queue`.

### Task 10: Network status, AI monitor and Offers pages

**Files:**
- Create: `frontend/app/dashboard/network/page.tsx`, `frontend/components/dashboard/network/*`, `frontend/app/dashboard/ai-monitor/page.tsx`, `frontend/components/dashboard/monitor/*`
- Rewrite: `frontend/components/dashboard/offers/{offers-view,offer-dialog}.tsx`, `frontend/lib/types/offer.ts` (or move offer types into `lib/types/admin.ts` and delete it)

**Interfaces / content:**
- Network (reference `page-network`): banner "Network operating normally" / "Service degraded in N districts"; tiles: active incidents, districts monitored, districts degraded; "Regional service health" grid (district, health chip); "Active incidents" list with Resolve button; "Stage incident" dialog: district (select from districts + free text), area, kind, status (investigating/scheduled), message, starts/ends (local time inputs). Errors from 422 show inline.
- AI monitor (reference `page-ai-monitor`): window toggle 24 h / 7 d; tiles: Chats, Resolution rate, Median first response (p95 underneath), Fallback rate (label "Turns answered without a tool"); "Most common intents" bars (share %); "Quality review queue" linking to `/dashboard/conversations/{id}`; "Audit trail" table (time, actor chip, action, subscriber masked, detail summary); "Guardrails & tools" static card listing: OTP required for writes (ON), payments (SIMULATED), support case creation (ON), human hand-off (CASE ONLY).
- Offers: list grouped or filterable by kind (Pack / Points / Cashback) with audience chip, active toggle, redemptions; dialog with kind selector that shows only that kind's fields, package select from `/admin/packages`, audience select with a subscriber multi-picker (search via `/admin/subscribers?q=`) for `specific`; 409 on delete shows "This offer has redemptions — deactivate it instead."

- [ ] **Step 1:** Invoke `frontend-design`, `ui-ux-pro-max`, `dataviz`.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`. Expected: no errors.
- [ ] **Step 4: Manual check:** stage an outage in Dhaka → Samiha's portal assistant, asked "আমার এলাকায় নেটওয়ার্ক সমস্যা?", reports it; resolve it → the agent no longer does (new question). A `specific` offer for Rafi appears in Rafi's portal Offers page and not in Samiha's.
- [ ] **Step 5: Commit** `feat(web): admin network staging, AI monitor and reshaped offers`.

### Task 11: Portal notification bell and nudge-started assistant sessions

**Files:**
- Create: `frontend/components/portal/shell/notification-bell.tsx`
- Modify: `frontend/components/portal/shell/topbar.tsx`, `frontend/lib/portal-api.ts`, `frontend/lib/types/portal.ts`, `frontend/lib/portal-sync.ts` (`PortalKey` gains `'notifications'`), `frontend/components/chat-bubble/chat-bubble-context.tsx`, `frontend/lib/visitor-id.ts` (session options), `frontend/app/api/token/route.ts`, `frontend/components/portal/assistant/assistant-provider.tsx`

**Interfaces / behaviour:**
- Bell in the topbar before the theme toggle: unread badge (hidden at 0, "9+" above 9); popover (sheet on phones) listing `items` with kind icon, title, body, relative time, unread dot; "Mark all read". Polls `GET /api/me/notifications` every 60 s while the tab is visible, and refetches on `telco.account_changed`.
- Click a notification: `POST …/{id}/read`, `invalidatePortal(['notifications'])`, then `startNudgeSession(id)` and navigate to `/portal/assistant`.
- `ChatBubbleContextValue.startNudgeSession(nudgeId: string): Promise<boolean>` — if a session is live, end it first (same path as `useEndSessionOnLogout`); set the nudge id so the session options carry `participantAttributes.nudge_id`; start a text session (`voice: false`); clear the nudge id once connected so the next session is a normal one.
- Token route: read the nudge from `body?.participant_attributes?.nudge_id` (keep `body?.nudge_id` too) and pass it to `buildDispatchMetadata` (already UUID-validated).
- The agent's first message is then the `greeting_nudge` greeting (backend already supports this).

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`. Expected: no errors.
- [ ] **Step 4: Manual check** (real stack: API, worker, LiveKit, scheduler not required): reset seed, run nudges from the control center, log in as Samiha → bell shows "Pack expiring"; click → assistant page opens and the agent's first line is about the expiring pack; the bell's badge drops by one; a second persona's notification id pasted into the body of `/api/token` does not change the greeting (agent log shows no nudge text).
- [ ] **Step 5: Commit** `feat(web): portal notification bell and nudge-started assistant sessions`.

### Task 12: Docs, frontend debt and carry-over bookkeeping

Carry-overs (phase 3): dead legacy files `chat-bubble.tsx`, `conversation-history.tsx`, `open-chat-button.tsx`; hard-coded hex colours (sidebar, icon-tile, assistant-chat, confirm-card); `frontend/DESIGN.md` still "Horizon Realty"; `TEMPLATE.md` still refers to `/home`.

**Files:**
- Delete: the three dead files if `grep` shows no imports (keep any that are imported).
- Modify: the four components with hex colours (replace with tokens from `globals.css`; add a token only when none fits), `frontend/DESIGN.md`, `TEMPLATE.md`, `README.md` (Admin portal section: routes, staging an incident, run nudges, notification bell; extend the demo checklist with admin steps: stage outage → ask agent, resolve case → bell, run nudges → click notification), memory files.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max` (for the token swaps).
- [ ] **Step 2: Implement.** `grep -rnE "#[0-9a-fA-F]{3,8}\b" frontend/components --include=*.tsx` shows no brand hex in those four files.
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint` and `uv run pytest -q` (from `backend/`). Expected: all green.
- [ ] **Step 4: Update memory:** new `telco-phase4-carryovers.md` (anything deferred in this phase) and remove resolved items from the phase 1/2/3 files; update `MEMORY.md`.
- [ ] **Step 5: Commit** `docs: phase 4 admin portal and nudges`.
