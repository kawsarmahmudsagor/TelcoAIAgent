# Telco Phase 3 — Customer Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A prospect picks one of 5 seeded personas and lands in a telco. self-care portal (overview, balance & usage, recharge, packages, offers, support, assistant). The portal runs on live `bss` data, its Recharge/Buy/Redeem buttons use the simulated OTP flow, and the AI assistant (bubble + full page, voice + chat) pushes cards and keeps the screen in sync.

**Architecture:**
- Backend:
  - A customer JWT in a separate `portal_session` cookie, issued by persona login, scopes new `/api/me/*` routes. Those routes call the same `bss` functions the agent tools call.
  - Portal writes are stateless start/confirm endpoints. The client re-sends the request with the code, and the OTP request hash rejects any change in between.
- Frontend:
  - The real-estate `(site)` group is replaced by a persona picker at `/` and a `/portal` route group.
  - The portal layout owns one LiveKit session, so a conversation survives page changes.
  - The Next `/api/token` route resolves `subscriber_id` server-side from the portal cookie and writes it into agent dispatch metadata.

**Tech Stack:**
- Backend: Python 3.11, FastAPI, SQLAlchemy 2, python-jose, pytest on real Postgres (`telco-pg`, port 5435), uv; LiveKit agents 1.7.
- Frontend: Next.js 15.5, React 19, Tailwind v4, livekit-client 2.22, @livekit/components-react 2.9, lucide-react, sonner, next-themes, pnpm.

**Spec:** `docs/superpowers/specs/2026-10-22-telco-agent-design.md` (sections 2, 6.1–6.4, 6.6, 8; Phase 3 in section 9). Carry-overs: memory files `telco-phase1-carryovers.md` and `telco-phase2-carryovers.md`; items folded in are named in each task. Reference UI: `C:\Users\BS23-DESKTOP-00038\Downloads\telco_dashboard.html` (customer mode only).

## Global Constraints

- Backend commands run from `backend/`: `uv run pytest -q`, `uv run alembic check`. Frontend commands run from `frontend/`: `pnpm typecheck` (added in Task 5) and `pnpm lint`.
- `subscriber_id` reaches the agent only through dispatch metadata written by the Next `/api/token` route from a verified `portal_session` cookie. Never take it from the request body, room config or browser metadata.
- Customer endpoints return only the token's own subscriber. Customer tokens are refused on admin endpoints, and admin tokens are refused on `/api/me/*`.
- Cookie names: admin `session` (unchanged), customer `portal_session`. JWT claims are `sub`, `role` (`admin` | `customer`), `exp`. A token without `role` counts as `admin`.
- OTP: 6 digits, 3-minute expiry, 3 attempts (`app.bss.otp`). Portal code throttle: 5 codes per 15 minutes per subscriber (same window as the agent's `CODE_WINDOW`).
- Recharge: ৳20–1000 per transaction, ৳5000 per day; target matches `^01[3-9]\d{8}$` (enforced in `bss`; the form pre-validates the same rule).
- Portal writes use `Actor.portal` and `CaseSource.portal`. Agent writes keep `Actor.agent`.
- Data topics (exact strings): `telco.account_changed`, `telco.otp_sms`, `telco.confirm`, plus `telco.packages` and `telco.case_created` (new in Task 4). RPC methods: `telco.confirm_action`, `telco.cancel_action`. Payload shapes are in memory `telco-phase2-carryovers.md` and Task 4.
- Agent name: `telco_agent` (backend `Settings.agent_name` and frontend `AGENT_NAME` default must match).
- Look (spec 6.6, values from the reference UI):
  - Colors: indigo `#4f46e5`, brand2 `#756cf6`, mint `#20b89a`, orange `#ff9b55`, red `#e45b73`.
  - Light: bg `#f5f7fb`, surface `#fff`, surface2 `#f8fafc`, text `#172033`, muted `#778198`, line `#e6eaf2`.
  - Dark: bg `#0b1020`, surface `#141b2d`, surface2 `#1a2338`, text `#f2f5ff`, muted `#9aa6c1`, line `#27314a`.
  - Radii: panel 17px, metric/offer 16px, hero 20px, buttons 10px.
  - Font: Inter.
  - Breakpoints: 1100px, 760px (off-canvas sidebar), 390px.
- Bangla-first copy where the reference has Bangla. Money is shown as `৳ 486.50` (2 dp when fractional, none when whole). Data is shown in GB with 1 dp at 1024 MB or more, otherwise MB.
- Every frontend task invokes the `frontend-design` and `ui-ux-pro-max` skills before editing, and ends with `pnpm typecheck` and `pnpm lint` passing.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Out of scope (Phase 4)

Notification bell and nudges (spec 7), admin pages, conversations API subscriber fields, `request_human_agent` idempotency, `pending_case` clearing, ActionRpc double-speak, R7 test isolation. Portal-side writes do not refresh an open agent session's snapshot; the agent's success text and tools re-read `bss`, so only the system-prompt snapshot is stale (accepted for the demo).

## Review Focus

1. **Forged identity to the agent.** A browser posts a `room_config` whose agent dispatch already carries `{"subscriber_id": "<someone else>"}`, or calls `/api/token` with no cookie. The agent must get the cookie's subscriber in the first case and a guest session (no `subscriber_id`) in the second. → Task 5 Step 6 manual check (curl + agent log) and Task 5 `buildDispatchMetadata` overwriting unconditionally.
2. **Request changed between start and confirm.** The client starts a ৳100 recharge, then confirms with `amount: 1000` and the right code. Expected: `400 otp_invalid` and no transaction. → Task 3 test `test_confirm_with_changed_request_is_rejected`.
3. **Cross-role cookies.** A customer cookie on `/api/conversations` gets 401, and an admin cookie on `/api/me` gets 401. → Task 1 tests `test_customer_token_refused_on_admin_route`, `test_admin_token_refused_on_me`.
4. **Double-click Confirm, or portal and agent confirming together.** The same `action_id` is confirmed twice. Expected: one transaction, and both responses carry the same `ref`. → Task 3 test `test_double_confirm_returns_same_ref`.
5. **Persona switch or logout during a live assistant call.** The LiveKit session is ended before the cookie changes, so the agent never keeps acting for the previous subscriber. → Task 10 Step 5 (`useEndSessionOnLogout`) and the Task 11 checklist line.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/services/auth_service.py` (modify) | role-aware tokens: `create_access_token(sub, role)`, `decode_access_token -> TokenClaims` |
| `backend/app/api/deps.py` (modify) | `get_current_admin` checks role; new `get_current_subscriber` |
| `backend/app/api/routes_demo.py` (create) | `/api/demo/personas`, `/login`, `/logout` |
| `backend/app/api/routes_me.py` (create) | `/api/me` profile and reads, `POST /api/me/cases` |
| `backend/app/api/routes_me_actions.py` (create) | `/api/me/actions/start`, `/api/me/actions/{id}/confirm` |
| `backend/app/api/bss_http.py` (create) | `BssError` → `HTTPException` map |
| `backend/app/api/schemas_me.py` (create) | request/response models for the portal routes |
| `backend/app/data/personas.py` (create) | persona msisdns + headlines (shared by seed and demo route) |
| `backend/app/bss/otp.py` (modify) | `normalise_code` (moved from agent), `issued_since` |
| `backend/app/agent/tools/packages.py`, `support.py`, `topics.py`, `snapshot.py`, `prompt_defaults.py`, `actions.py`; `backend/app/config.py` (modify) | new card topics, snapshot fix, refs digits rule, agent name |
| `frontend/app/(site)/**`, `frontend/components/{home,properties,property,offers}/**`, `frontend/lib/{public-listings,property-filters,offers}.ts`, apartment/booking cards (delete) | real-estate leftovers |
| `frontend/app/page.tsx`, `frontend/components/portal/persona-picker.tsx` (create) | `/` persona login |
| `frontend/styles/globals.css`, `frontend/app/layout.tsx` (modify) | telco tokens, Inter, metadata |
| `frontend/lib/portal-api.ts`, `frontend/lib/types/portal.ts`, `frontend/lib/telco-format.ts` (create) | typed `/api/me` client + formatters |
| `frontend/lib/portal-sync.ts` (create) | `usePortalQuery` + `invalidatePortal()` bus |
| `frontend/app/api/token/route.ts`, `frontend/lib/agent-dispatch.ts`, `frontend/middleware.ts` (modify/create) | server-side subscriber metadata; `/portal` gate |
| `frontend/app/portal/layout.tsx`, `frontend/components/portal/shell/*` (create) | sidebar, topbar, drawer, theme, profile/logout |
| `frontend/app/portal/{page,balance,recharge,packages,offers,support,assistant}/page.tsx`, `frontend/components/portal/*` (create) | pages and widgets |
| `frontend/components/portal/actions/*` (create) | portal OTP dialog + SMS toast |
| `frontend/components/portal/assistant/*`, `frontend/lib/telco-topics.ts` (create) | shared session provider, bubble, full page, telco card hooks |

---

### Task 1: Customer auth and demo personas

Carry-over (phase 1): "set subscriber_id … server-side from persona login, never from the browser" (backend half).

**Files:**
- Create: `backend/app/data/personas.py`, `backend/app/api/routes_demo.py`, `backend/tests/test_portal_auth.py`
- Modify: `backend/app/services/auth_service.py`, `backend/app/api/deps.py`, `backend/app/api/routes_auth.py`, `backend/app/main.py`, `backend/app/data/seed_telco.py` (import msisdns from `personas.py` instead of repeating them), `backend/tests/conftest.py`

**Interfaces:**
- Produces:
  - `TokenClaims(BaseModel){sub: str, role: Literal["admin","customer"]}`.
  - `create_access_token(sub: str, role: Literal["admin","customer"] = "admin") -> str`.
  - `decode_access_token(token: str) -> TokenClaims | None`.
  - `PORTAL_COOKIE = "portal_session"` in `deps.py`.
  - `get_current_subscriber(request: Request, db: Session = Depends(get_db)) -> uuid.UUID`: 401 if the cookie is missing or invalid, the role is not `customer`, or the subscriber row is gone.
  - `PERSONA_HEADLINES: dict[str, str]` (msisdn → one-line English headline), with keys exactly the 5 seed msisdns `01712342841, 01812347392, 01912345501, 01612341109, 01512346620`.
  - Routes, all `Cache-Control: no-store`:
    - `GET /api/demo/personas` → `list[PersonaCard{msisdn, masked_msisdn, full_name, plan_type, district, headline}]`, in seed order, only rows that exist.
    - `POST /api/demo/login {msisdn}` → sets the `portal_session` cookie (httponly, samesite=lax, max_age = `jwt_expire_minutes*60`) and returns `PortalMe` (Task 2 defines it; it lives in `schemas_me.py`, so create that file here with `PortalMe{subscriber_id, full_name, first_name, msisdn, masked_msisdn, plan_type, district}`). A msisdn that is not one of the 5 personas gets 404.
    - `POST /api/demo/logout` → deletes the cookie and returns `{ok: true}`.
  - Fixture `customer_api(subscriber_id)` in `conftest.py`: a factory returning a `TestClient` with `get_current_subscriber` overridden to that id.

- [ ] **Step 1: Write failing tests** in `tests/test_portal_auth.py`:

```python
def test_personas_lists_seeded_five_in_order(anon_api): ...
    # msisdns == ["01712342841","01812347392","01912345501","01612341109","01512346620"]; headline non-empty
def test_login_sets_portal_cookie_and_me_works(anon_api): ...
    # POST /api/demo/login {"msisdn":"01712342841"} -> 200, body.full_name == "Samiha Khan",
    # "portal_session" in r.cookies; then GET /api/me with that client -> 200, same subscriber_id
def test_login_unknown_or_non_persona_msisdn_404(anon_api, bss_world): ...
    # "01700000000" -> 404; a bss_world subscriber's msisdn (01999…) -> 404
def test_customer_token_refused_on_admin_route(anon_api): ...
    # log in as persona, then GET /api/conversations -> 401 (cookie "session" set to the customer token too)
def test_admin_token_refused_on_me(anon_api): ...
    # client.cookies.set("portal_session", create_access_token("ceo")) -> GET /api/me 401
def test_role_less_token_is_admin(): ...
    # jose-encode {"sub":"ceo","exp":...} -> decode_access_token(...).role == "admin"
def test_logout_clears_cookie(anon_api): ...
```

`GET /api/me` and `/api/me/summary` come from Task 2. For now, register a minimal `GET /api/me` in `routes_me.py` so these tests run. Task 2 extends that file.

- [ ] **Step 2: Run** `uv run pytest tests/test_portal_auth.py -q`. Expected: FAIL (404s / import errors).
- [ ] **Step 3: Implement.** In `routes_auth.py` and every other caller of `decode_access_token`, use `.sub`. In `get_current_admin`, return `claims.sub` only when `role == "admin"`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass (existing admin tests unchanged).
- [ ] **Step 5: Commit** `feat(api): customer persona login and role-aware tokens`.

### Task 2: Portal read API

**Files:**
- Create/extend: `backend/app/api/routes_me.py`, `backend/app/api/schemas_me.py`, `backend/tests/test_portal_reads.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `get_current_subscriber` (Task 1); `bss.accounts`, `packages`, `transactions`, `rewards`, `cases`, `network` (signatures in `app/bss/*`).
- Produces: routes under `/api/me`. All are scoped to the token's subscriber, use `Cache-Control: no-store`, and return the `bss` Pydantic types as JSON, with Decimals serialised as numbers:
  - `GET ""` → `PortalMe`.
  - `GET /summary` → `AccountSummary`.
  - `GET /usage?period_days=7` → `UsageBreakdown`. `period_days` is 1–90, default 30. Optional `kind`.
  - `GET /transactions?type=&status=&days=30&limit=20` → `list[TransactionView]`. `limit` ≤ 50, `days` ≤ 90.
  - `GET /packages?kind=` → `list[PackageView]`.
  - `GET /recommendations` → `list[Recommendation]`.
  - `GET /offers` → `OffersAndPoints`.
  - `GET /cases` → `list[CaseView]` (limit 20, newest first).
  - `POST /cases {category, description, priority="normal", request_id: UUID}` → `201 CaseView`. It calls `bss.cases.create_case(..., source=CaseSource.portal, action_id=request_id)`, so a repeat `request_id` returns the same case. `category` is one of `PORTAL_CASE_CATEGORIES = ("recharge_not_credited","unexpected_deduction","package_activation","network_issue","billing","other")`. `description` is 10–1000 chars after strip; anything else → 422.
  - `GET /network` → `list[IncidentView]` for the subscriber's own district.
  - Numeric JSON: configure Decimals to serialise as floats, via `PlainSerializer` on response models or a `json_encoders`-free approach of the implementer's choice. Pinned by the test below.

- [ ] **Step 1: Write failing tests** in `tests/test_portal_reads.py`. Use `bss_world` subscribers and `customer_api`:

```python
def test_summary_is_own_subscriber(bss_world, customer_api): ...
    # two subs A,B; customer_api(A.id).get("/api/me/summary").json()["subscriber_id"] == str(A.id)
def test_money_is_json_number(bss_world, customer_api): ...
    # isinstance(summary["main_balance"], (int, float))
def test_usage_period_bounds(bss_world, customer_api): ...  # period_days=0 -> 422, 91 -> 422, 7 -> 200 and body.period_days == 7
def test_transactions_only_own(bss_world, customer_api): ...  # B's txn ref absent from A's list
def test_create_case_idempotent_on_request_id(bss_world, customer_api): ...
    # same body twice -> same ref; GET /cases has exactly one; case.source == "portal"
def test_create_case_rejects_unknown_category_and_short_text(bss_world, customer_api): ...  # 422 each
def test_network_defaults_to_own_district(bss_world, customer_api): ...
def test_me_routes_need_customer(anon_api): ...  # parametrised over every GET path -> 401
```

- [ ] **Step 2: Run** `uv run pytest tests/test_portal_reads.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the routes; map `BssError` with `bss_http_error` (create `app/api/bss_http.py` here, see Task 3 Interfaces for the table).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(api): customer portal read endpoints`.

### Task 3: Portal write flow (start / confirm)

Carry-over (phase 1): "throttle OTP issue at portal endpoints".

**Files:**
- Create: `backend/app/api/routes_me_actions.py`, `backend/tests/test_portal_actions.py`
- Modify: `backend/app/bss/otp.py` (add `normalise_code`, `issued_since`), `backend/app/agent/actions.py` (import `normalise_code` from `bss.otp`, drop its own copy), `backend/app/api/schemas_me.py`, `backend/app/api/bss_http.py`, `backend/app/main.py`, `backend/tests/test_bss_otp.py`

**Interfaces:**
- Produces:
  - `otp.normalise_code(raw: str) -> str`: same behavior as the agent's current function (Bengali digits, spaces and dashes accepted).
  - `otp.issued_since(db, subscriber_id: UUID, since: datetime) -> int`: counts `OtpChallenge` rows with `created_at >= since`. The portal always uses a fresh `action_id`, so rows equal issues.
  - `PortalAction`: a Pydantic discriminated union on `kind`:
    - `{kind: "purchase", package_code: str, pay_from: TxnChannel}`
    - `{kind: "recharge", amount: Decimal, channel: TxnChannel, target_msisdn: str | None}`
    - `{kind: "redeem", offer_id: UUID}`
  - `POST /api/me/actions/start` body `PortalAction` → `ActionStart{action_id, kind, title, amount: float|None, pay_from: str|None, target: str|None, points_cost: int|None, expires_at, otp: {code, to (masked msisdn), expires_at}}`.
    - It runs the matching `bss.preview_*`, then `otp.issue(purpose=kind, payload=<request>.model_dump(mode="json"))`, the same purpose/payload the `execute_*` functions check.
    - `title`: package name (purchase), `"Recharge ৳<amount>"` (recharge) or the offer title (redeem).
    - Throttle: if `issued_since(now − 15 min) >= 5` → `429 {code: "too_many_codes"}` before issuing.
    - The code in the response is the simulated SMS (demo only, same as the agent's `telco.otp_sms`).
  - `POST /api/me/actions/{action_id}/confirm` body `{action: PortalAction, code: str}` → `ActionResult{kind, ref, main_balance: float|None, postpaid_due: float|None, reward_points: int|None}`.
    - It runs `otp.verify(..., code=normalise_code(code))`, then `execute_*(..., action_id, actor=Actor.portal)`, in one DB session, and commits.
  - `bss_http_error(e: BssError) -> HTTPException` with `detail={"code": e.code, "message": e.message}`. Status by code:
    - 404: `subscriber_not_found`, `package_not_found`, `case_not_found`, `no_pending_action`
    - 409: `insufficient_balance`, `insufficient_points`, `offer_not_eligible`
    - 422: `limit_exceeded`, `invalid_msisdn`, `invalid_request`
    - 400: `otp_invalid`
    - 410: `otp_expired`
    - 429: `otp_attempts_exceeded`

- [ ] **Step 1: Write failing tests** in `tests/test_portal_actions.py`, plus `test_normalise_code_*` and `test_issued_since_counts_window` in `test_bss_otp.py`:

```python
def test_recharge_start_then_confirm_credits_balance(bss_world, customer_api): ...
    # start {"kind":"recharge","amount":100,"channel":"bkash"} -> otp.code 6 digits;
    # confirm with same action + code -> ref startswith "TXN-"; main_balance == old + 100
def test_purchase_from_balance(bss_world, customer_api): ...
def test_redeem_with_points(bss_world, customer_api): ...  # reward_points decreased by points_cost
def test_confirm_with_changed_request_is_rejected(bss_world, customer_api): ...
    # start amount 100, confirm amount 1000 + right code -> 400 detail.code == "otp_invalid"; no new transaction
def test_double_confirm_returns_same_ref(bss_world, customer_api): ...
def test_wrong_code_three_times_locks(bss_world, customer_api): ...  # 400,400,429(otp_attempts_exceeded)
def test_sixth_code_in_15_minutes_is_throttled(bss_world, customer_api): ...  # 5 starts ok, 6th -> 429 too_many_codes
def test_insufficient_balance_is_409(bss_world, customer_api): ...
def test_recharge_bad_target_is_422(bss_world, customer_api): ...  # target "0123" -> invalid_msisdn
def test_bengali_digit_code_accepted(bss_world, customer_api): ...  # code given as Bengali digits with a space
def test_portal_transaction_audit_actor_is_portal(bss_world, customer_api, db): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_portal_actions.py tests/test_bss_otp.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass, including the agent `test_actions.py` after the `normalise_code` move.
- [ ] **Step 5: Commit** `feat(api): portal OTP start/confirm for purchase, recharge, redeem`.

### Task 4: Agent cards and pre-demo fixes

Carry-overs (phase 2): "digits rule should exempt TC-/TXN- refs"; "snapshot turns a logged-in customer into guest on any network-lookup failure"; "Settings.agent_name still real_estate_agent". Spec 6.3 topics `telco.packages` and `telco.case_created`.

**Files:**
- Modify: `backend/app/agent/topics.py`, `backend/app/agent/tools/packages.py`, `backend/app/agent/tools/support.py`, `backend/app/agent/snapshot.py`, `backend/app/agent/prompt_defaults.py`, `backend/app/config.py`, `backend/.env.example` (if it names `AGENT_NAME`)
- Test: `backend/tests/test_tools_read.py`, `backend/tests/test_tools_write.py`, `backend/tests/test_snapshot.py`, `backend/tests/test_prompts.py`

**Interfaces:**
- Produces:
  - `topics.PACKAGES = "telco.packages"`, payload `{title: str, packages: [{code, name, kind, data_mb, minutes, sms, validity_days, price: float, tag: str|None}]}` (max 6).
    - Sent by `run_search_packages` (title `"Packages"`) and `run_recommend_packages` (title `"Recommended for you"`) when the list is non-empty.
  - `topics.CASE_CREATED = "telco.case_created"`, payload `{ref, category, priority, status, created_at (ISO)}`.
    - Sent by `run_create_support_case` (after the confirmed create) and `run_request_human_agent`, alongside the existing `account_changed`.
  - `Settings.agent_name` default `"telco_agent"`.
  - Prompt: the numbers rule's English-digits exception now reads "except phone numbers and references such as TC-2048 or TXN-840219, which are always English digits …".
  - `load_session_context`: a failure in `network.check_network_status` no longer escapes. The snapshot line becomes `"Network status in <district> is unavailable right now."` and the customer stays logged in.

- [ ] **Step 1: Write failing tests:**
  - `test_search_packages_publishes_cards` (fake publish captures `(topic, payload)`; `payload["packages"][0]["price"]` is float).
  - `test_empty_search_publishes_nothing`.
  - `test_create_case_publishes_case_created`.
  - `test_human_agent_publishes_case_created`.
  - `test_snapshot_survives_network_failure` (monkeypatch `network.check_network_status` to raise; `subscriber_id` kept, text contains "unavailable").
  - `test_prompt_refs_use_english_digits` (the base prompt contains "TC-2048").
  - `test_default_agent_name` (`Settings().agent_name == "telco_agent"`, with `AGENT_NAME` unset via monkeypatch).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass. If `scripts/router_bench`/`word_checks` assert on prompt text, update them.
- [ ] **Step 5: Commit** `feat(agent): package and case cards; snapshot and prompt fixes`.

### Task 5: Frontend foundation — cleanup, tokens, persona login, token route

Carry-over (phase 1): "subscriber_id in LiveKit metadata server-side" (frontend half). Spec 6.1 "Removed" row (the `(site)` part; dashboard pages are Phase 4).

**Files:**
- Delete:
  - `frontend/app/(site)/**`
  - `frontend/components/{home,properties,property,offers}/**`
  - `frontend/lib/{public-listings,property-filters,offers}.ts`
  - `frontend/lib/types/property.ts`, if nothing outside `dashboard/properties` imports it. Otherwise leave it for Phase 4.
- Create:
  - `frontend/app/page.tsx`, `frontend/components/portal/persona-picker.tsx`
  - `frontend/lib/types/portal.ts`, `frontend/lib/portal-api.ts`, `frontend/lib/telco-format.ts`
  - `frontend/lib/agent-dispatch.ts`
- Modify:
  - `frontend/package.json` (add `"typecheck": "tsc --noEmit"`)
  - `frontend/next.config.ts` (drop the `/` → `/home` redirect and the unsplash image pattern)
  - `frontend/app/layout.tsx` (Inter via `next/font/google`, metadata title `telco.`, description "telco. self-care portal and AI assistant (demo)")
  - `frontend/styles/globals.css`
  - `frontend/app-config.ts` (telco. name, accent `#4f46e5`, dark accent `#756cf6`, `agentName: 'telco_agent'`)
  - `frontend/middleware.ts`
  - `frontend/app/api/token/route.ts`

**Interfaces:**
- Produces:
  - `lib/types/portal.ts`: TS mirrors of `PortalMe`, `PersonaCard`, `AccountSummary`, `SubscriptionView`, `UsageBreakdown`, `TransactionView`, `PackageView`, `Recommendation`, `OffersAndPoints`, `OfferView`, `CaseView`, `IncidentView`, `PortalAction`, `ActionStart`, `ActionResult`. Field names match the backend JSON exactly; `daily` is `[string, number][]`.
  - `lib/portal-api.ts`: `portalApi = { personas(), login(msisdn), logout(), me(), summary(), usage(periodDays), transactions(params?), packages(kind?), recommendations(), offers(), cases(), createCase(body), network(), startAction(a), confirmAction(actionId, a, code) }`. It is built on the existing `apiFetch`. Errors surface as `ApiError` with `.code` taken from `detail.code` (extend `ApiError` with an optional `code`).
  - `lib/telco-format.ts`:
    - `formatTaka(n: number): string` → `"৳ 486.50"` / `"৳ 500"`.
    - `formatData(mb: number): string` → `"8.4 GB"` / `"800 MB"`.
    - `formatDay(iso: string): string` → `"22 Oct"`.
    - `maskMsisdn` is not needed (the backend sends `masked_msisdn`).
  - `lib/agent-dispatch.ts`: `buildDispatchMetadata(subscriberId: string | null, extras: {visitorId?: string; nudgeId?: string}): string` → JSON `{channel: "inbound_chat", subscriber_id?, visitor_id?, nudge_id?}`. `nudge_id`/`visitor_id` are kept only if they match a UUID regex.
  - Token route:
    - Resolves the subscriber by server-side `fetch(${FASTAPI_INTERNAL_URL}/api/me, {headers: {cookie: "portal_session=<value>"}})`. A non-200 response (or no cookie) means a guest.
    - Then **overwrites** `metadata` on every agent dispatch (or creates the one dispatch) with `buildDispatchMetadata(...)`, ignoring any metadata the client sent.
    - `AGENT_NAME` default `'telco_agent'`. `nudge_id` comes from the request body.
  - Middleware: the matcher adds `/portal/:path*`. Without a `portal_session` cookie, `/portal/*` redirects to `/`. The `/dashboard` behavior is unchanged.
  - Tokens in `globals.css`:
    - Re-skin `:root`/`.dark` shadcn variables to the telco palette (Global Constraints).
    - Add `--surface2`, `--line`, `--mint`, `--orange`, `--red`, `--brand2` and the tint pairs from the reference: purple `#efedff`/`#302d5b`, green `#e2faf4`/`#183f3b`, orange `#fff0e3`/`#4a3328`, pink `#ffeaf0`/`#4b2735`; status chips success/pending/failed/open.
    - Expose them in `@theme inline` as `--color-*`.
    - Keep the `data-surface` blocks working for the dashboard.
  - Persona picker at `/`:
    - Brand mark plus 5 persona cards (name, masked number, plan chip, district, headline). Clicking a card calls `portalApi.login` and then `router.push('/portal')`.
    - Footer links "Admin login" → `/login`.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`. Read the reference HTML sections for tokens and sidebar.
- [ ] **Step 2:** Delete the leftovers; fix imports (`chat-bubble-context.tsx` loses listing-focus bits only if they come from deleted files; the card cleanup itself is Task 10).
- [ ] **Step 3:** Implement the files above.
- [ ] **Step 4: Run** `pnpm typecheck && pnpm lint`. Expected: no errors.
- [ ] **Step 5: Manual check:**
  - With backend + `pnpm dev`, `/` lists the 5 personas, and Samiha → `/portal` (404 page is fine until Task 6).
  - `/portal` without the cookie redirects to `/`.
- [ ] **Step 6: Manual security check** (Review Focus 1):
  - `curl -X POST localhost:3001/api/token -H 'content-type: application/json' -d '{"room_config":{"agents":[{"agent_name":"telco_agent","metadata":"{\"subscriber_id\":\"00000000-0000-0000-0000-000000000001\"}"}]}}'` → decode the returned JWT (`roomConfig.agents[0].metadata`). It has no `subscriber_id`.
  - With a persona cookie, it has that persona's id.
  - Record both outputs in the task report.
- [ ] **Step 7: Commit** `feat(web): persona login, telco tokens, server-side agent identity`.

### Task 6: Portal shell and live-sync data layer

**Files:**
- Create: `frontend/app/portal/layout.tsx`, `frontend/components/portal/shell/{sidebar,topbar,mobile-drawer,profile-menu,nav-items}.tsx`, `frontend/lib/portal-sync.ts`, `frontend/components/portal/ui/{panel,metric-tile,status-chip,progress-bar,section-head,icon-tile}.tsx`, `frontend/components/portal/portal-me-context.tsx`

**Interfaces:**
- Produces:
  - `lib/portal-sync.ts`:
    - `usePortalQuery<T>(key: PortalKey, fetcher: () => Promise<T>): {data?: T; error?: ApiError; loading: boolean; reload(): void}`.
    - `invalidatePortal(keys?: PortalKey[]): void` (no args = all).
    - `PortalKey = 'me'|'summary'|'usage'|'transactions'|'packages'|'recommendations'|'offers'|'cases'|'network'`.
    - Implementation: a module-level `EventTarget`. Each query refetches on a matching invalidation and keeps the previous `data` while refetching, so cards don't flash.
    - A 401 from any query sends the browser to `/`.
  - `PortalMeProvider` / `usePortalMe(): PortalMe` (loaded once in the layout; the layout shows a spinner until loaded).
  - UI primitives match the reference patterns: metric tile, status chip tones `success|pending|failed|open`, 6px progress bar in `brand|mint|orange`, panel r17.
  - Sidebar items (label → route, lucide icon):
    - Overview `/portal` (Home)
    - Balance & usage `/portal/balance` (Gauge)
    - Recharge & bills `/portal/recharge` (ArrowUpRight)
    - My packages `/portal/packages` (Package)
    - Offers & rewards `/portal/offers` (Gift)
    - Support cases `/portal/support` (LifeBuoy)
    - AI assistant `/portal/assistant` (Sparkles, mint dot)
  - Sidebar also has the "MY ACCOUNT" label, the help-card "Need a hand?" with "Chat with Telco AI" → `/portal/assistant`, and the profile row (initials avatar, name, masked number · plan).
  - There is no Customer/Admin mode switch in Phase 3; an "Admin" link in the profile menu goes to `/login`.
  - Topbar: the eyebrow "Your digital life, made easier", the page title (from `nav-items`), a theme toggle (`next-themes`), and the profile menu with "Switch persona" and "Log out". Both call `portalApi.logout()`, then `router.push('/')`.
  - Mobile ≤760px: the sidebar becomes an off-canvas drawer (260px) behind a menu button.
  - Placeholders: each route under `/portal/*` exists with its title so navigation works. Later tasks fill them.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2:** Implement.
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`. Expected: no errors.
- [ ] **Step 4: Manual check:**
  - Every sidebar link resolves.
  - Dark/light both readable.
  - At 760px the drawer opens/closes and has no horizontal scroll.
  - Logout returns to `/`, and `/portal` then redirects.
- [ ] **Step 5: Commit** `feat(web): portal shell, theme and live-sync query layer`.

### Task 7: Overview and Balance & usage pages

**Files:**
- Create: `frontend/app/portal/page.tsx`, `frontend/app/portal/balance/page.tsx`, `frontend/components/portal/overview/{balance-hero,allowances-card,metrics-row,quick-actions,usage-chart,recent-activity,made-for-you}.tsx`, `frontend/components/portal/balance/{detail-cards,usage-breakdown,keep-active}.tsx`

**Interfaces:**
- Consumes: `usePortalQuery`, `portalApi.summary/usage/transactions/recommendations`, `formatTaka/formatData/formatDay`, `usePortalMe`.

Content mapping (reference sections "Overview" and "Balance & usage"; numbers come from live data, not the reference's sample values):
- **Welcome row.** "Good morning/afternoon/evening, <first_name>" by local hour, plus the date pill. Asia/Dhaka.
- **Balance hero.**
  - Prepaid shows `main_balance`. Postpaid shows "Bill due" `postpaid_due`.
  - The label reads "PREPAID ACCOUNT · <masked_msisdn>".
  - Buttons: "Recharge now" → `/portal/recharge`, "View details" → `/portal/balance`.
- **Allowances.**
  - Lines for data, minutes and SMS: left vs total of active subscriptions.
  - Totals: `SubscriptionView` has only `package_code` and amounts left, so join each `package_code` against `portalApi.packages()` for `data_mb`/`minutes`/`sms`. The bar shows left/total; an unknown code shows the amount left with no bar.
  - With no active pack, show "No active pack" with a "Buy a pack" link.
- **Metrics row.**
  - Data used (usage 30d data total).
  - Minutes used (voice total).
  - Active pack expires (`nearest_expiry`, "N days left").
  - Rewards (`reward_points`).
- **Quick actions.** The 4 shortcuts from the reference. "Ask Telco AI" → `/portal/assistant`.
- **Usage chart.**
  - Inline SVG area/line of `usage(7)` or `usage(30)` `daily` data (MB → GB), with a 7/30-day select.
  - No chart library. The axis is in GB.
  - An accessible `<title>` plus visually-hidden table summary.
- **Recent activity.** Last 5 transactions, with sign by type (recharge `+`, purchase/redeem `−`; redeem shown in points when the channel is `points`) and a status chip.
- **Made for you.** Top 3 `recommendations`. "Get pack" → `/portal/packages?highlight=<code>`.
- **Balance page.**
  - Detail cards: main balance, internet left, talk-time left, each with expiry.
  - "Usage breakdown" from `usage(30).totals` (data, voice, sms, vas, with charge).
  - "Keep your pack active" for the nearest-expiring subscription, with "Renew pack" → `/portal/packages?highlight=<package_code>` and the auto-renew state shown read-only.
- **States.** Loading skeletons, an error panel with retry, and empty states for zero transactions or zero subscriptions.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2:** Implement.
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`.
- [ ] **Step 4: Manual check:**
  - Samiha (prepaid, pack expiring) and Nusrat (postpaid, bill due) both render correct figures against `GET /api/me/summary`.
  - Rafi shows his ৳42.00 balance.
  - Mobile 390px has no overflow.
- [ ] **Step 5: Commit** `feat(web): portal overview and balance pages`.

### Task 8: Recharge, Packages and Offers pages with the portal OTP flow

Spec 6.4.

**Files:**
- Create:
  - `frontend/app/portal/{recharge,packages,offers}/page.tsx`
  - `frontend/components/portal/actions/{use-portal-action.ts,otp-dialog.tsx,sms-toast.tsx}`
  - `frontend/components/portal/recharge/{recharge-form,recent-recharges}.tsx`
  - `frontend/components/portal/packages/{package-grid,package-card}.tsx`
  - `frontend/components/portal/offers/{points-metrics,offer-card}.tsx`

**Interfaces:**
- Consumes: `portalApi.startAction/confirmAction/packages/offers/transactions`, `invalidatePortal`.
- Produces:
  - `usePortalAction(): { start(a: PortalAction): Promise<void>; dialog: ReactNode }`. `dialog` is rendered once per page. Shared by Task 10 (not reused by the agent cards — they use RPC).
  - `showSmsToast({code, to, expiresAt})`. A sonner custom toast styled as a phone SMS: "telco. OTP: <code> — valid 3 min. Never share it." It stays until dismissed or expiry. Exported for Task 10.

Flow:
1. The button calls `start`.
2. `startAction` → `showSmsToast(otp)` and opens `OtpDialog`. The dialog shows the title, amount/points, pay-from, a 6-box code input (paste fills all; Bengali digits accepted as typed), a countdown to `expires_at`, and Cancel / Confirm.
3. Confirm → `confirmAction(action_id, sameAction, code)`.
   - Success: close, toast "Done — ref <ref>", `invalidatePortal()`.
   - `otp_invalid`: inline "Wrong code", attempts left (3 − n).
   - `otp_expired`/`otp_attempts_exceeded`: show the message and close.
   - `too_many_codes`: toast "Too many codes — try again in a few minutes".
   - Other errors: show `message`.
4. The Confirm button disables while in flight (Review Focus 4).

Pages:
- **Recharge.**
  - Number field: default own `msisdn`, validates `^01[3-9]\d{8}$`.
  - Amount chips ৳100/200/300/500 plus custom (20–1000).
  - Channel bKash/Nagad/Card.
  - "Continue to payment" → `start({kind: "recharge", ...})`, with `target_msisdn` omitted when it is the own number.
  - "Demo only — no real payment" note.
  - Right column: recent recharges (`transactions({type: "recharge", limit: 5})`), and "Need help with a recharge?" → `/portal/assistant?q=<prefill>`.
  - Postpaid: the heading becomes "Pay your bill", the amount is prefilled with `postpaid_due` (capped at 1000), and it uses the same flow.
- **Packages.**
  - Filters All / Internet (data) / Minutes (voice) / Bundles (bundle) / SMS.
  - 3-column card grid (2 at ≤1100px, 1 at ≤760px). Each card: tag, name, contents, validity, price, "Buy pack".
  - Buy opens a small chooser for pay-from (`balance` labelled "Main balance" for prepaid and "Add to bill" for postpaid, `bkash`, `nagad`, `card` — the backend's `_PAY_CHANNELS`), then `start`.
  - `?highlight=<code>` scrolls to and rings that card.
- **Offers.**
  - Metrics: points, offer count, points to the cheapest points offer ("N points to your next reward", or "Enough for a reward").
  - Offer cards from `offers()`. Points offers get "Redeem" → `start({kind: "redeem", offer_id})`, disabled with "Need N more points" when short. Cashback offers get "Recharge" → `/portal/recharge`. Package offers get "Get pack" → packages highlight.
  - Reward activity: `transactions({type: "redeem"})`.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2:** Implement.
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`.
- [ ] **Step 4: Manual check:**
  - Recharge ৳100 as Rafi: toast shows the code, enter it, the balance updates on Overview without reload.
  - A wrong code shows attempts left.
  - Buy as Samiha from balance.
  - Redeem 1 GB as Farhana.
  - Buy something too expensive as Rafi shows the insufficient-balance message.
- [ ] **Step 5: Commit** `feat(web): recharge, packages and offers with portal OTP flow`.

### Task 9: Support cases page

**Files:**
- Create: `frontend/app/portal/support/page.tsx`, `frontend/components/portal/support/{case-metrics,case-table,new-case-dialog}.tsx`

**Interfaces:**
- Consumes: `portalApi.cases/createCase/network`, `invalidatePortal(['cases','summary'])`.

Content:
- **Metrics.** All cases, Open (`open` + `in_review`), Resolved, "Typical response ~2 hrs" (static).
- **Table "Your requests".**
  - Columns Case ID / Issue (category label + description, truncated) / Created / Last update / Status.
  - Status chips: `open` → open, `in_review` → pending, `resolved` → success.
  - Mobile: stacked cards instead of a table at ≤760px.
- **"New case" dialog.**
  - Category select over `PORTAL_CASE_CATEGORIES`, with labels:
    - "Recharge not credited"
    - "Unexpected deduction"
    - "Package activation"
    - "Network issue"
    - "Billing"
    - "Other"
  - Description textarea (10–1000 chars, counter) and priority normal/high.
  - `request_id = crypto.randomUUID()` is generated when the dialog opens, so a double submit is idempotent.
  - Success toast "Case <ref> created".
- **Network panel.** Incidents in the subscriber's district from `network()` ("No known issues in <district>" when empty).
- **"Need help now?"** → `/portal/assistant`.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2:** Implement.
- [ ] **Step 3: Run** `pnpm typecheck && pnpm lint`.
- [ ] **Step 4: Manual check:**
  - Farhana shows 1 resolved and 1 open.
  - Create a case and it appears at the top.
  - Tanvir sees the Sylhet congestion.
- [ ] **Step 5: Commit** `feat(web): portal support cases`.

### Task 10: Assistant — shared session, page, bubble and telco cards

Spec 6.3.

**Files:**
- Create:
  - `frontend/components/portal/assistant/{assistant-provider,assistant-page,assistant-bubble,suggested-questions}.tsx`
  - `frontend/lib/telco-topics.ts`
  - `frontend/components/portal/assistant/cards/{confirm-card,package-cards,case-card}.tsx`
  - `frontend/app/portal/assistant/page.tsx`
- Modify: `frontend/app/portal/layout.tsx`, `frontend/components/agents-ui/blocks/agent-session-view-01/components/agent-session-block.tsx`, `frontend/components/app/call/call-overlay.tsx`, `overlay-order.ts`, `chat-bubble-context.tsx`, `frontend/components/agents-ui/agent-chat-transcript.tsx`
- Delete: `frontend/components/app/{apartment-card,apartment-shortlist,booking-form-card}.tsx` and the real-estate topic hooks in `lib/livekit-text-streams.ts` (`apartment-shortlist`, `listing-focus`, `booking-form`). Keep `user-turn`/`ignored-text`.

**Interfaces:**
- Consumes:
  - Topic payloads in memory `telco-phase2-carryovers.md` and Task 4.
  - `showSmsToast` (Task 8), `invalidatePortal` (Task 6).
  - The existing `ChatBubbleProvider`/`ViewController`/`useSession` pattern. Reuse it: the portal layout mounts one provider, so both the bubble and `/portal/assistant` render the same session.
- Produces, in `lib/telco-topics.ts` (each `room.registerTextStreamHandler` mounted exactly once, inside the provider):
  - `useTelcoTopics(room, agentState)`.
    - It exposes `cards: TelcoCard[]` (ordered with the transcript the way `placeShortlistResults` did) and `confirm: ConfirmState | null`.
    - It handles:
      - `telco.otp_sms` → `showSmsToast`.
      - `telco.confirm` → upsert by `action_id`; the latest `state` wins.
      - `telco.packages` → a package-cards entry.
      - `telco.case_created` → a case card.
      - `telco.account_changed` → `invalidatePortal()`.
    - New cards are held until the agent speaks, with the existing `FALLBACK_REVEAL_MS`. `confirm` and `account_changed` apply immediately.
    - It resets on `RoomEvent.Disconnected`.
  - **ConfirmCard.**
    - Title, amount (or "<points> points" for redeem), pay-from, target, a countdown, a 6-box code input, Confirm / Cancel.
    - Confirm → `performRpc({destinationIdentity: agent.identity, method: 'telco.confirm_action', payload: JSON.stringify({action_id, code})})`. Parse `{ok, error}` and show `error` inline when not ok.
    - Cancel → `telco.cancel_action {action_id}`.
    - States `done`/`cancelled`/`expired` render read-only with the ref when present.
  - **PackageCards.** A horizontal scroller of compact package cards. "Buy" sends a chat message through the session's text input: `` `I want to buy ${name} (${code})` `` (so the agent runs `purchase_package` and its own confirm card). It does not call the portal API.
  - **CaseCard.** Ref, category, status chip, "View in Support" → `/portal/support`.
  - `useEndSessionOnLogout()`: the profile menu's logout/switch calls `session.end()` (if connected) before `portalApi.logout()` (Review Focus 5).
  - **Assistant page.**
    - Reference "AI assistant" layout: chat panel (header "Telco AI Assistant", ● Online) plus a 280px aside, "Popular questions" and "I can help you with".
    - Popular-question chips send text:
      - "How much data do I have left?"
      - "Which package is best for me?"
      - "Why was my balance deducted?"
      - "Create a support case"
      - "আমার ব্যালেন্স কত?"
    - Mic toggle (voice) and text input share one session.
    - Footer note "Never share your OTP or payment PIN in chat."
    - `?q=` prefills the input (Task 8 link).
  - **Bubble.** A floating launcher on every `/portal/*` page except `/portal/assistant`. Its panel reuses the same session. "Open full view" → `/portal/assistant` keeps the conversation.

- [ ] **Step 1:** Invoke `frontend-design` and `ui-ux-pro-max`.
- [ ] **Step 2:** Remove the real-estate cards and hooks; fix the overlay order and transcript references.
- [ ] **Step 3:** Implement the provider, topics, cards, page and bubble.
- [ ] **Step 4: Run** `pnpm typecheck && pnpm lint`.
- [ ] **Step 5: Manual check** (backend, agent worker and `pnpm dev` running):
  - As Samiha, ask "আমার ব্যালেন্স কত?" and get a Bangla answer with live numbers.
  - "Show me data packs" shows package cards. Buy → confirm card + SMS toast. Enter the code on the card → done. The balance on Overview updates without reload.
  - The same via voice code.
  - Navigate Overview → Packages while connected, and the call continues.
  - Open the bubble, then "Open full view", and the transcript is kept.
  - Log out mid-call: the session ends before the persona picker shows.
  - Log in as Rafi: the agent greets Rafi, not Samiha.
- [ ] **Step 6: Commit** `feat(web): portal assistant with telco cards and live sync`.

### Task 11: Docs and carry-over bookkeeping

**Files:**
- Modify: `README.md` (customer portal section: personas, `/` → `/portal`, how to run agent + backend + frontend, demo-script checklist), `backend/app/agent` nothing.
- Memory (controller, not the implementer): update `telco-phase1-carryovers.md` / `telco-phase2-carryovers.md` and add `telco-phase3-carryovers.md`.

- [ ] **Step 1:** README demo checklist (one line each):
  - persona login
  - overview figures
  - portal recharge with OTP toast
  - assistant Bangla balance question
  - package cards → buy via confirm card
  - live update
  - case via assistant appears on Support
  - Tanvir network question
  - persona switch ends the call
- [ ] **Step 2: Run** `uv run pytest -q` (backend) and `pnpm typecheck && pnpm lint && pnpm build` (frontend). Expected: all green.
- [ ] **Step 3: Commit** `docs: phase 3 customer portal`.
