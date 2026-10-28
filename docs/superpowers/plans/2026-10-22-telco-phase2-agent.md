# Telco Phase 2 — Agent Tools, OTP Flow and Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the LiveKit agent into the telco assistant: 17 tools over the `bss` seam, the preview → OTP → confirm → execute write flow (voice, chat and on-screen card), an account snapshot in the system prompt, telco prompts everywhere, seeded KB docs and a router eval set.

**Architecture:** Tools live in `app/agent/tools/*`; each is a thin `function_tool` wrapper around an `async def run_<name>(userdata, ...) -> str` that resolves the session's `subscriber_id`, calls `bss` in a worker thread with its own DB session, maps `BssError` to guidance text, and pushes UI events on room data topics. Pending writes live in `SessionUserdata.pending_action` (one at a time) and are confirmed by `verify_otp` or by the confirm card's RPC; `bss` idempotency on `action_id` makes the two paths safe together.

**Tech Stack:** Python 3.11, LiveKit agents 1.7, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pytest on real Postgres (`telco-pg`, port 5435), uv. Frontend: Next.js (Task 3 only).

**Spec:** `docs/superpowers/specs/2026-10-22-telco-agent-design.md` (sections 2, 4, 5, 8; Phase 2 in section 9). Phase 1 carry-overs: memory file `telco-phase1-carryovers.md` (Phase 2 items folded in below).

## Global Constraints

- Run everything from `backend/`: tests `uv run pytest -q`, migrations `uv run alembic upgrade head`, drift `uv run alembic check`.
- Tools never import from `app.repositories` or touch models directly for writes: reads and writes go through `app.bss`.
- Customer reads/writes are scoped to the session's `subscriber_id`; the only other number allowed is a recharge target.
- OTP: 6 digits, 3-minute expiry, 3 attempts (`app.bss.otp.OTP_TTL`, `MAX_ATTEMPTS`).
- Recharge: ৳20–1000 per transaction, ৳5000 per day; target matches `^01[3-9]\d{8}$` (enforced in `bss.recharge`).
- One pending write per session; a new write request replaces the pending one and the tool output says so.
- Never claim success before `bss.execute_*` returns. The OTP code is never put in tool output or prompt text; it only reaches the browser on `telco.otp_sms`.
- Data topics (exact strings): `telco.account_changed`, `telco.otp_sms`, `telco.confirm`. RPC methods: `telco.confirm_action`, `telco.cancel_action`.
- No stack traces or exception text reach the user: every `BssError` maps to a fixed guidance string.
- Tool output is English facts/instructions for the LLM; the LLM speaks in the customer's language (Bangla-first, mirror per turn, Banglish → Bangla in Bengali script).
- Money in tool text: `format_amount` (e.g. `486.50 taka`, `500 taka`); data: `format_data` (e.g. `15.2 GB`, `800 MB`).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Frontend tasks invoke the `frontend-design` and `ui-ux-pro-max` skills before editing, then pass `npm run typecheck` and `npm run lint` in `frontend/`.

## Review Focus

1. **Guest or unknown subscriber session** (no `subscriber_id`, or a UUID with no row): every account tool returns the not-logged-in guidance; nothing raises. → Task 4 test `test_tools_without_subscriber_say_log_in`, Task 8 test `test_unknown_subscriber_becomes_guest`.
2. **OTP said with Bengali digits or separators** ("১২৩ ৪৫৬", "123-456", "123 456"): normalised to 6 ASCII digits before verify. → Task 6 test `test_verify_otp_accepts_bengali_digits_and_spaces`.
3. **Voice `verify_otp` and card RPC confirming the same action at once:** exactly one transaction; both callers report success. → Task 7 test `test_rpc_and_voice_confirm_race_creates_one_transaction`.
4. **New write while one is pending:** the old action is cancelled (card state `cancelled`), its OTP can no longer execute it, and the tool output tells the LLM it was replaced. → Task 6 test `test_new_write_replaces_pending_action`.
5. **Stale snapshot after a write:** the system-prompt snapshot still shows the old balance; the success text carries the new balance and says the snapshot is out of date. → Task 6 test `test_success_text_overrides_snapshot`.

## File Structure

| File | Responsibility |
|---|---|
| `app/bss/errors.py`, `app/bss/otp.py` (modify) | `InvalidRequest`; OTP re-issue and verified-window policy |
| `migrations/versions/d4e8a1c2f7b3_agent_config_telco.py` (create) | agent_config renames, `greeting_nudge`, drop cold-call/follow-up |
| `app/agent/telco_format.py` (create) | `format_amount`, `format_data`, `format_day` |
| `app/agent/topics.py` (create) | topic / RPC name constants and payload builders |
| `app/agent/tools/_common.py` (create) | subscriber guard, `run_db`, `ERROR_TEXT`, `error_text` |
| `app/agent/tools/account.py`, `packages.py`, `recharge.py`, `transactions.py`, `rewards.py`, `support.py`, `network.py`, `verify.py` (create) | tools (logic `run_*` + `function_tool` wrapper) |
| `app/agent/tools/registry.py` (create) | `telco_tools() -> list` |
| `app/agent/actions.py` (create) | `PendingAction`, `start_action`, `confirm_action`, `cancel_action` |
| `app/agent/action_rpc.py` (create) | `ActionRpc`: the confirm card's RPC methods |
| `app/agent/snapshot.py` (create) | `load_session_context` → customer name, snapshot text, nudge text |
| `app/agent/prompt_defaults.py`, `persona.py`, `entrypoint.py`, `userdata.py`, `session_context.py` (modify) | telco prompts, snapshot injection, greetings, tool + RPC registration |
| `app/agent/turn_router.py`, `turn_judge.py`, `prefetch.py`, `quick_reply.py`, `gated_agent.py`, `app/services/voice_preview.py`, `app/agent/tools/search_knowledge_base.py` (modify) | internal prompts → telco |
| `app/data/kb/*.md`, `app/data/seed_kb.py` (create), `app/data/seed_all.py` (modify) | KB seed docs |
| `scripts/router_bench/cases.json` (rewrite), `tests/test_router_bench_cases.py` (create) | conversation eval set |

---

### Task 1: bss hardening (InvalidRequest, OTP policy)

Carry-overs: ValueError mapping; OTP re-issue resets attempts; consumed challenges never expire; missing cross-subscriber / purpose-mismatch tests.

**Files:**
- Modify: `app/bss/errors.py`, `app/bss/accounts.py:115`, `app/bss/cases.py:63`, `app/bss/packages.py:137`, `app/bss/recharge.py:73`, `app/bss/otp.py`
- Test: `tests/test_bss_otp.py`, `tests/test_bss_accounts.py:54`, `tests/test_bss_cases_network.py:129`, `tests/test_bss_packages.py:94`, `tests/test_bss_recharge.py:55`

**Interfaces:**
- Produces: `class InvalidRequest(BssError)` with `code = "invalid_request"`, `default_message = "Invalid request"`. `otp.require_verified(db, *, subscriber_id, action_id, purpose, payload, now: datetime | None = None) -> None`.

- [ ] **Step 1: Write failing tests** in `tests/test_bss_otp.py`:

```python
def test_verify_other_subscribers_action_is_no_pending(bss_world, db): ...
    # issue for sub A; verify(subscriber_id=B.id, same action_id, right code) -> NoPendingAction
def test_purpose_mismatch_counts_attempt(bss_world, db): ...
    # issue purpose="purchase"; verify(purpose="recharge", right code) -> OtpInvalid; row.attempts == 1
def test_reissue_keeps_attempt_count(bss_world, db): ...
    # issue, 2 wrong verifies, issue again (same action_id) -> row.attempts == 2;
    # one more wrong verify -> OtpInvalid; next verify with the new right code -> OtpAttemptsExceeded
def test_require_verified_expires_three_minutes_after_consumption(bss_world, db): ...
    # verify at t0; require_verified(now=t0 + 2m59s) passes; now=t0 + 3m01s -> OtpExpired
```
Change the four `pytest.raises(ValueError)` lines to `pytest.raises(InvalidRequest)`.

- [ ] **Step 2: Run** `uv run pytest tests/test_bss_otp.py tests/test_bss_accounts.py tests/test_bss_cases_network.py tests/test_bss_packages.py tests/test_bss_recharge.py -q` — expect the new tests and the four changed ones to FAIL.

- [ ] **Step 3: Implement.** Add `InvalidRequest`; replace the four `raise ValueError(...)` with `raise InvalidRequest(...)` (same messages). In `otp.issue`: if the row exists and `attempts >= MAX_ATTEMPTS` raise `OtpAttemptsExceeded`; do not reset `attempts`. In `otp.require_verified`: add `now`; after the existing checks raise `OtpExpired` when `row.consumed_at + OTP_TTL < now`. Callers in `packages/recharge/rewards.execute_*` pass their `now` through.

- [ ] **Step 4: Run** the full suite `uv run pytest -q` — expect PASS (821 + 4).

- [ ] **Step 5: Commit** `fix(bss): InvalidRequest for bad input, OTP re-issue keeps attempts, verified window`.

---

### Task 2: agent_config → telco fields

Spec 5.1: rename `agency_name` → `operator_name`, add `greeting_nudge`, drop `greeting_coldcall` / `greeting_followup`. Ruling: `agency_phone` / `agency_address` also become `operator_phone` / `operator_address` (consistent naming; cost if wrong: a rename back). `agency_timezone` / `agency_tz` stay as they are.

**Files:**
- Create: `migrations/versions/d4e8a1c2f7b3_agent_config_telco.py` (down_revision = current head; check with `uv run alembic heads`)
- Modify: `app/models/agent_config.py`, `app/config.py:154-159`, `app/schemas/agent_config.py`, `app/services/agent_config_service.py`, `app/api/routes_agent_config.py`, `app/agent/prompt_defaults.py` (PLACEHOLDERS, DEFAULTS, placeholder names inside existing default texts only — copy rewrite is Task 8), `app/agent/persona.py`, `app/agent/entrypoint.py` (`_greet` values), `app/services/voice_preview.py:56`, `../.env.example:173-178`, `../.env` (same keys, local only, git-ignored)
- Test: `tests/test_agent_config.py`, `tests/test_build_llm.py`, `tests/test_voice_preview.py`, `tests/test_greeting_guard.py`, `tests/test_prompts.py`, `tests/test_speech_numbers.py:109`

**Interfaces:**
- Produces: `ResolvedAgentConfig.operator_name / operator_phone / operator_address / greeting_nudge`; no `agency_*`, `greeting_coldcall`, `greeting_followup`. Settings `database_url` default becomes `postgresql+psycopg://telco:telco@localhost:5435/telco` (leftover). Settings `operator_name="telco"`, `operator_phone="01700121121"`, `operator_address="telco Experience Centre, Gulshan Avenue, Dhaka 1212"` (env `OPERATOR_NAME`, `OPERATOR_PHONE`, `OPERATOR_ADDRESS`). `PLACEHOLDERS`:
  - `prompt_identity_rules`: `{"agent_name", "operator_name", "current_date", "timezone", "knowledge_scope"}`
  - `greeting_inbound`: `{"agent_name", "operator_name", "customer_name"}`
  - `greeting_nudge`: `{"agent_name", "operator_name", "customer_name", "nudge_text"}`
- API: GET/PATCH `/api/agent-config` expose `operator_name`, `operator_phone`, `operator_address`, `greeting_nudge`, `greeting_nudge_is_default`; `greeting_coldcall*` / `greeting_followup*` gone.

- [ ] **Step 1: Update tests first.** Rename fields in the tests listed. Add to `tests/test_agent_config.py`:

```python
def test_greeting_nudge_placeholders_validated(api):
    ok = api.patch("/api/agent-config", json={"greeting_nudge": "Hi {customer_name}: {nudge_text}"})
    assert ok.status_code == 200
    bad = api.patch("/api/agent-config", json={"greeting_nudge": "Hi {client_name}"})
    assert bad.status_code == 422

def test_greeting_inbound_rejects_old_agency_placeholder(api):
    assert api.patch("/api/agent-config", json={"greeting_inbound": "{agency_name}"}).status_code == 422

def test_removed_greetings_not_in_api(api):
    body = api.get("/api/agent-config").json()
    assert "greeting_coldcall" not in body and "greeting_followup" not in body
```
`tests/test_speech_numbers.py`: rename to `test_default_operator_phone_is_said_as_a_phone_number`, `spoken = "zero one seven double zero one two double one two one"`.

- [ ] **Step 2: Run** `uv run pytest tests/test_agent_config.py tests/test_speech_numbers.py -q` — expect FAIL.

- [ ] **Step 3: Migration.** `alter_column` renames for the three `agency_*` columns; `add_column greeting_nudge Text NULL`; `drop_column greeting_coldcall, greeting_followup`; `UPDATE agent_config SET prompt_identity_rules = replace(prompt_identity_rules, '{agency_name}', '{operator_name}'), greeting_inbound = replace(greeting_inbound, '{agency_name}', '{operator_name}')`. Downgrade reverses (re-adding dropped columns as NULL).

- [ ] **Step 4: Rename through model, settings, schemas, service, routes, persona, entrypoint, voice_preview, env files.** In `_greet`, values become `{"agent_name", "operator_name", "customer_name": ""}` for now (Task 8 fills the name).

- [ ] **Step 5: Run** `uv run alembic upgrade head && uv run alembic check && uv run pytest -q` — expect PASS, "No new upgrade operations detected".

- [ ] **Step 6: Commit** `feat(config): operator_* fields and greeting_nudge; drop cold-call greetings`.

---

### Task 3: Dashboard config editor follows the rename

Mechanical frontend follow-up of Task 2 plus one new editor field. Invoke `frontend-design` and `ui-ux-pro-max` first; match the existing template-editor pattern exactly (no restyle).

**Files:**
- Modify: `frontend/lib/types/agent-config.ts`, `frontend/components/dashboard/chatbot/config-draft.ts`, `frontend/components/dashboard/chatbot/agent-tab.tsx`, `frontend/components/dashboard/chatbot/template-editor.tsx`, `frontend/lib/types/public.ts`, `frontend/lib/types/schedule.ts`, `frontend/app/dashboard/incoming/[id]/page.tsx`

**Interfaces:**
- Consumes: Task 2 API field names.

- [ ] **Step 1:** Replace `agency_name/phone/address` with `operator_*` (labels "Operator name", "Hotline number", "Address"). Remove the cold-call and follow-up greeting editors. Add a "Nudge greeting" editor for `greeting_nudge`, placeholders `agent_name, operator_name, customer_name, nudge_text`, using the same component and reset-to-default behaviour as `greeting_inbound`. In `public.ts` / `schedule.ts` / incoming page, rename the field references only (those pages are rebuilt in Phase 3/4).
- [ ] **Step 2: Run** in `frontend/`: `npm run typecheck && npm run lint` — expect no errors.
- [ ] **Step 3: Commit** `feat(dashboard): operator fields and nudge greeting in the prompt editor`.

---

### Task 4: Tool foundation

**Files:**
- Create: `app/agent/telco_format.py`, `app/agent/topics.py`, `app/agent/tools/_common.py`
- Modify: `app/agent/userdata.py`
- Test: `tests/test_telco_format.py`, `tests/test_tool_common.py`

**Interfaces:**
- Produces:
  - `format_amount(amount: Decimal) -> str` — `Decimal("486.5")` → `"486.50 taka"`, `Decimal("500")` → `"500 taka"`, `Decimal("1240")` → `"1,240 taka"`.
  - `format_data(mb: int) -> str` — `< 1024` → `"800 MB"`; else GB with one decimal, trailing `.0` dropped: `15565` → `"15.2 GB"`, `1024` → `"1 GB"`.
  - `format_day(when: datetime, *, with_time: bool = False) -> str` — Asia/Dhaka, `"Friday 24 October"`; `with_time=True` adds `", 14:30"`.
  - `topics.py`: `ACCOUNT_CHANGED = "telco.account_changed"`, `OTP_SMS = "telco.otp_sms"`, `CONFIRM = "telco.confirm"`, `RPC_CONFIRM = "telco.confirm_action"`, `RPC_CANCEL = "telco.cancel_action"`; `async def publish(userdata, topic: str, payload: dict) -> None` (JSON, `send_text` directly, not deferred; logs and swallows send failures).
  - `_common.py`: `NOT_LOGGED_IN: str`; `def subscriber_id_or_none(userdata) -> UUID | None`; `async def run_db(fn: Callable[[Session], T]) -> T` (`asyncio.to_thread`, own `SessionLocal()`, closed after; rollback on exception); `ERROR_TEXT: dict[str, str]` keyed by every `BssError` subclass `code`; `def error_text(err: BssError) -> str`.
  - `SessionUserdata` new fields: `pending_action: "PendingAction | None" = None`, `pending_case: "CaseDraft | None" = None`, `offer_ids: list[UUID]` (default empty), `otp_issued_at: list[datetime]` (default empty), `action_lock: asyncio.Lock` (default factory), `snapshot_text: str | None = None`, `customer_name: str | None = None`, `nudge_text: str | None = None`.

`ERROR_TEXT` guidance (each: reason + next step, English, no codes): `insufficient_balance` → offer a recharge first; `package_not_found` → offer search_packages; `limit_exceeded` → state limits ৳20–1000 per recharge, ৳5000 per day, or too many codes requested, try later; `invalid_msisdn` → ask for an 11-digit number starting 01; `otp_expired` → action cancelled, offer to start again; `otp_invalid` → code didn't match, ask them to check the on-screen SMS and say it again; `otp_attempts_exceeded` → too many wrong codes, action cancelled, offer to start again; `no_pending_action` → nothing awaiting a code; `offer_not_eligible`, `insufficient_points`, `case_not_found`, `subscriber_not_found` (→ NOT_LOGGED_IN), `invalid_request` → ask the customer to rephrase what they want.

- [ ] **Step 1: Write failing tests:**

```python
def test_every_bss_error_has_guidance():
    codes = {c.code for c in _all_subclasses(BssError)}
    assert codes <= ERROR_TEXT.keys()

def test_error_text_hides_internal_message():
    assert "Traceback" not in error_text(InsufficientBalance("balance 3.20 < 49"))
    assert "3.20" not in error_text(InsufficientBalance("balance 3.20 < 49"))

def test_tools_without_subscriber_say_log_in():  # Review Focus 1, extended in Tasks 5-6
    assert subscriber_id_or_none(SessionUserdata(channel=Channel.inbound_chat, room=None)) is None

@pytest.mark.parametrize("value,expected", [(Decimal("486.5"), "486.50 taka"), (Decimal("500"), "500 taka"), (Decimal("1240"), "1,240 taka")])
def test_format_amount(value, expected): ...

@pytest.mark.parametrize("mb,expected", [(800, "800 MB"), (1024, "1 GB"), (15565, "15.2 GB")])
def test_format_data(mb, expected): ...

def test_publish_swallows_send_failure(): ...  # room whose send_text raises -> no exception
```

- [ ] **Step 2: Run** `uv run pytest tests/test_telco_format.py tests/test_tool_common.py -q` — expect FAIL (import errors).
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** the same tests, then `uv run pytest -q` — expect PASS.
- [ ] **Step 5: Commit** `feat(agent): tool foundation (format, topics, bss error guidance)`.

---

### Task 5: Read tools

Tool output: English fact lines for the LLM, amounts/data via Task 4 formatters, at most the first 3 packages/transactions in detail plus a count of the rest. Every tool starts with the subscriber guard (except `search_packages`, which reads the public catalogue) and turns `BssError` into `ToolError(error_text(err))`.

**Files:**
- Create: `app/agent/tools/account.py`, `packages.py` (read half), `transactions.py`, `rewards.py` (read half), `support.py` (read half), `network.py`, `registry.py`
- Test: `tests/test_tools_read.py`

**Interfaces:**
- Consumes: Task 4; `bss.accounts.get_account_summary / get_usage_breakdown / explain_deductions`, `bss.packages.search / recommend`, `bss.transactions.lookup`, `bss.rewards.get_offers_and_points`, `bss.cases.get_case_status`, `bss.network.check_network_status`.
- Produces (logic functions; each tool is `@function_tool()` wrapping the same name without `run_`, docstring = LLM description, args documented):
  - `run_get_account_summary(userdata) -> str`
  - `run_get_usage_breakdown(userdata, period_days: int = 30, kind: str | None = None) -> str` (period 7 or 30)
  - `run_explain_deductions(userdata, days: int = 7) -> str` (spec `since?` → days back; ruling: easier for the LLM)
  - `run_search_packages(userdata, kind: str | None = None, max_price: float | None = None, min_data_gb: float | None = None, validity_days: int | None = None) -> str`; also a sync `search_packages_text(db, **args) -> str` used by the prefetcher (Task 9)
  - `run_recommend_packages(userdata) -> str`
  - `run_lookup_transactions(userdata, type: str | None = None, status: str | None = None, ref: str | None = None, days: int = 30) -> str`
  - `run_get_offers_and_points(userdata) -> str` — numbers offers `#1..#n` and stores their ids in `userdata.offer_ids`
  - `run_get_case_status(userdata, ref: str | None = None) -> str`
  - `run_check_network_status(userdata, district: str | None = None) -> str` — defaults to the subscriber's district; guest without district → asks which district
  - `registry.telco_tools() -> list` — all Task 5 and Task 6 tools (Task 6 appends its own)

- [ ] **Step 1: Write failing tests** (real DB via `bss_world`, fake userdata `SessionUserdata(channel=Channel.inbound_chat, room=_FakeRoom(), subscriber_id=sub.id)`):

```python
async def test_account_summary_text_has_balance_and_pack(bss_world): ...
    # prepaid, main_balance 486.50, 15 GB pack -> "486.50 taka" and "15 GB" in text, masked number, no full msisdn
async def test_postpaid_summary_shows_bill_due(bss_world): ...
async def test_search_packages_filters_and_caps_detail(bss_world): ...
    # 5 matching data packs -> 3 described, "2 more" mentioned; inactive package never listed
async def test_offers_are_numbered_and_remembered(bss_world): ...
async def test_check_network_defaults_to_subscriber_district(bss_world): ...
async def test_get_case_status_unknown_ref_maps_error(bss_world): ...  # ToolError with ERROR_TEXT["case_not_found"]
async def test_bad_period_maps_invalid_request(bss_world): ...          # period_days=14 -> ToolError(ERROR_TEXT["invalid_request"])
async def test_tools_without_subscriber_say_log_in(): ...               # every account tool -> NOT_LOGGED_IN, no DB call
async def test_reads_scoped_to_session_subscriber(bss_world): ...       # txn of sub B never appears for sub A
```

- [ ] **Step 2: Run** `uv run pytest tests/test_tools_read.py -q` — expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [ ] **Step 5: Commit** `feat(agent): telco read tools`.

---

### Task 6: Write flow and write tools

**Files:**
- Create: `app/agent/actions.py`, `app/agent/tools/recharge.py`, `app/agent/tools/verify.py`
- Modify: `app/agent/tools/packages.py`, `rewards.py`, `support.py`, `registry.py`
- Test: `tests/test_actions.py`, `tests/test_tools_write.py`

**Interfaces:**
- Consumes: Tasks 1, 4, 5; `bss.packages.preview_purchase / execute_purchase`, `bss.recharge.preview_recharge / execute_recharge`, `bss.rewards.preview_redeem / execute_redeem`, `bss.otp.issue / verify`, `bss.cases.create_case / request_human_agent`.
- Produces:

```python
ActionKind = Literal["purchase", "recharge", "redeem"]

@dataclass
class PendingAction:
    action_id: UUID
    kind: ActionKind
    request: PurchaseRequest | RechargeRequest | UUID   # UUID = offer id
    payload: dict          # what the OTP binds: request.model_dump(mode="json") or {"offer_id": str}
    card: dict             # title, amount, pay_from, target (recharge), expires_at (ISO)

@dataclass
class CaseDraft:
    action_id: UUID
    category: str
    description: str
    priority: CasePriority

MAX_CODES_PER_WINDOW = 5
CODE_WINDOW = timedelta(minutes=15)

async def start_action(userdata, kind: ActionKind, request) -> str
async def confirm_action(userdata, code: str, *, action_id: UUID | None = None) -> str
async def cancel_action(userdata, *, action_id: UUID | None = None) -> str
def normalise_code(raw: str) -> str   # Bengali digits -> ASCII, drop non-digits
```

Flow (spec 4.2):
- `start_action`: guard subscriber; throttle (`otp_issued_at` within `CODE_WINDOW` ≥ `MAX_CODES_PER_WINDOW` → `ToolError(ERROR_TEXT["limit_exceeded"])`); `preview_*` in `run_db`; new `action_id`; `otp.issue(purpose=kind, payload=payload)`; if a different action was pending, publish its card with `state="cancelled"` and prefix the result with "The earlier pending <kind> was cancelled and replaced."; set `userdata.pending_action`; publish `telco.otp_sms` `{action_id, code, to: masked_msisdn, expires_at}` and `telco.confirm` `{action_id, kind, state: "awaiting_code", ...card}`. Return: quote facts + "A 6-digit code was sent to the customer's screen. State the price and how they pay, then ask them to say or type the code, or tap Confirm. Never read the code aloud."
- `confirm_action`: under `userdata.action_lock`; no pending (or `action_id` given and different) → `NoPendingAction`; `otp.verify` with the normalised code; on `OtpExpired` / `OtpAttemptsExceeded` clear pending and publish card `state="expired"` / `"cancelled"`; `OtpInvalid` keeps it pending; then `execute_*` (`actor=Actor.agent`); clear pending; publish card `state="done"` with `ref`, and `telco.account_changed` `{kind, ref}`. Return result facts (ref, new balance / due / points / expiry) + "These figures replace the account snapshot in your instructions."
- `cancel_action`: clears the pending action, publishes card `state="cancelled"`.
- Tools: `purchase_package(package_code: str, pay_from: str = "balance")`, `start_recharge(amount: float, channel: str, msisdn: str | None = None)`, `redeem_reward(offer_number: int)` (resolves `userdata.offer_ids`; unknown number → `ToolError` telling the LLM to call `get_offers_and_points` first), `verify_otp(code: str)`, `cancel_pending_action()` (ruling: the customer saying "cancel" needs a tool; spec lists none; cost if wrong: one extra tool), `create_support_case(category: str, description: str, priority: str = "normal", confirmed: bool = False)`, `request_human_agent(reason: str)`.
- `create_support_case`: `confirmed=False`, or no `pending_case` with the same category and description → store a `CaseDraft` and return "Read back the category and description and ask the customer to confirm; then call again with confirmed=true." `confirmed=True` with a matching draft → `create_case(source=CaseSource.agent, action_id=draft.action_id)`, clear the draft, publish `account_changed` `{kind: "case", ref}`.
- `request_human_agent`: `bss.cases.request_human_agent(source=agent, action_id=uuid4())`; returns the case ref and "A human agent will follow up on this case; there is no live transfer."
- Purchase with `InsufficientBalance`: the tool text adds the shortfall and "Offer a recharge first (start_recharge)."

- [ ] **Step 1: Write failing tests** (`bss_world`, fake room recording `(topic, json)`; OTP code read from the recorded `telco.otp_sms` payload):

```python
async def test_purchase_needs_code_then_executes(bss_world): ...
    # start -> no transaction yet; topics [otp_sms, confirm(awaiting_code)]; code not in returned text
    # confirm_action(code) -> one success transaction; topics end with confirm(done), account_changed{kind:"purchase"}
async def test_execute_refused_without_verified_code(bss_world): ...   # wrong code -> ToolError(otp_invalid), no transaction
async def test_verify_otp_accepts_bengali_digits_and_spaces(bss_world): ...  # "১২৩ ৪৫৬" style of the real code -> done
async def test_new_write_replaces_pending_action(bss_world): ...
    # start purchase A, start recharge B -> card A cancelled; text says replaced; A's code via confirm_action(action_id=A) -> NoPendingAction
async def test_expired_code_cancels_action(bss_world, monkeypatch): ...  # utc_now + 4 min -> card state expired, pending None
async def test_three_wrong_codes_cancel_action(bss_world): ...
async def test_code_throttle(bss_world): ...                            # 6th start within 15 min -> ToolError(limit_exceeded)
async def test_insufficient_balance_suggests_recharge(bss_world): ...
async def test_success_text_overrides_snapshot(bss_world): ...           # new balance in text + "replace the account snapshot"
async def test_recharge_other_number(bss_world): ...                     # target "01812345678" accepted; "0123" -> invalid_msisdn guidance
async def test_redeem_by_offer_number(bss_world): ...
async def test_support_case_needs_confirmation(bss_world): ...           # first call no case; second confirmed call one case; third confirmed call same ref (replay)
async def test_human_agent_opens_high_priority_case(bss_world): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_actions.py tests/test_tools_write.py -q` — expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [ ] **Step 5: Commit** `feat(agent): OTP-gated write flow and write tools`.

---

### Task 7: Confirm card RPC and session wiring

**Files:**
- Create: `app/agent/action_rpc.py`
- Modify: `app/agent/entrypoint.py` (restore `_linked_identity` from commit `7da8acd`, `backend/app/agent/entrypoint.py:725-740` — `git show 7da8acd:backend/app/agent/entrypoint.py`; `_session_tools` adds `registry.telco_tools()`; register `ActionRpc` after `session.start`)
- Test: `tests/test_action_rpc.py`, `tests/test_prompts.py` (`test_session_tools_*`)

**Interfaces:**
- Consumes: Task 6 `confirm_action`, `cancel_action`; `topics.RPC_CONFIRM / RPC_CANCEL`.
- Produces: `class ActionRpc(session, userdata, room, linked_identity: Callable[[], str | None])` with `register()`, `async confirm(data) -> str`, `async cancel(data) -> str`, `async settle()` (tests). Replies JSON `{"ok": bool, "error": str | None}`; never raises. Caller identity ≠ linked → `{"ok": false, "error": "Not allowed."}`. Payload `{"action_id": str, "code": str}`. After a successful confirm it calls `session.generate_reply(instructions="The customer confirmed on the card. <result text> Tell them briefly it's done.")`, not awaited; on a `BssError` it answers `{"ok": false, "error": <short English reason>}` and asks the session to tell the customer (`generate_reply` with `error_text`).

- [ ] **Step 1: Write failing tests:**

```python
async def test_rpc_wrong_caller_refused(bss_world): ...
async def test_rpc_confirm_executes_and_speaks(bss_world): ...   # fake session records generate_reply instructions
async def test_rpc_stale_action_id(bss_world): ...                # payload action_id != pending -> ok false
async def test_rpc_and_voice_confirm_race_creates_one_transaction(bss_world): ...
    # asyncio.gather(confirm_action(code), rpc.confirm(payload with code)) -> 1 Transaction row for action_id; both ok
async def test_rpc_cancel(bss_world): ...
```
In `tests/test_prompts.py`, the session-tools test expects `{"end_call"} | TELCO_TOOL_NAMES` (16 names: the 15 spec 4.1 tools other than `search_knowledge_base`, plus `cancel_pending_action`) and the knowledge base on top when RAG is on.

- [ ] **Step 2: Run** `uv run pytest tests/test_action_rpc.py tests/test_prompts.py -q` — expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [ ] **Step 5: Commit** `feat(agent): confirm card RPC and telco tools in the session`.

---

### Task 8: Snapshot, system prompt and greetings

Carry-overs: prompt_defaults / search_knowledge_base description still real-estate.

**Files:**
- Create: `app/agent/snapshot.py`
- Modify: `app/agent/prompt_defaults.py` (rewrite all copy), `app/agent/persona.py`, `app/agent/entrypoint.py` (`entrypoint`, `_greet`), `app/agent/tools/search_knowledge_base.py` (module doc, `_POINT_TO_TEAM`, tool description)
- Test: `tests/test_snapshot.py`, `tests/test_prompts.py`, `tests/test_greeting_guard.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class SessionContext:
    subscriber_id: UUID | None      # None when the id was missing or unknown (guest)
    customer_name: str | None       # first name
    snapshot: str                   # GUEST_SNAPSHOT for guests
    nudge_text: str | None

def load_session_context(subscriber_id: UUID | None, nudge_id: UUID | None, *, now: datetime | None = None) -> SessionContext
```
  Snapshot (spec 5.2), English, labelled sample data: name, masked number, plan type, district, main balance (prepaid) or bill due (postpaid), each active pack with data/minutes/SMS left and expiry day, reward points, open case count, active incidents in the district (area, kind, status). `nudge_text`: only when the `notifications` row exists and belongs to the subscriber; text by kind from its payload (`pack_expiring`, `low_balance`, `low_data`, `case_update`).
- `build_system_prompt(userdata, config=None, *, rag_tool_available=False) -> str` appends `userdata.snapshot_text` (or `GUEST_SNAPSHOT`) after the identity block.
- `entrypoint`: after `session_context.resolve`, `ctx = await asyncio.to_thread(load_session_context, ...)`; copy into userdata (`subscriber_id` replaced by `ctx.subscriber_id`, `customer_name`, `snapshot_text`, `nudge_text`) before `_build_session`. On any exception log and continue as guest.
- `_greet`: values `{"agent_name", "operator_name", "customer_name": first name or ""}`; with `userdata.nudge_text` uses `greeting_nudge` (template or `DEFAULT_GREETING_NUDGE`) through `generate_reply`, adding `nudge_text`; otherwise inbound: default → canned `SPOKEN_GREETINGS_INBOUND` (named) or `SPOKEN_GREETINGS_GUEST` (no name); custom → `generate_reply`. Salam rule unchanged.
- `prompt_defaults` rewrite, following spec 5.3 sections 1–9 in order (section 10 stays `_BROWSER_END_NOTE`): identity ({agent_name}, digital assistant of {operator_name}, Bangladesh mobile operator, demo with sample data); language (keep the existing Bangla-first / Banglish / unsupported-language / digits rules; units টাকা, জিবি, এমবি, মিনিট; phone numbers in English digits); voice style (1–2 sentences, no lists or markdown, one question, at most 3 packages then offer more); scope (account, packages, recharge, transactions, offers/rewards, support, network, telco FAQ; one-line redirect otherwise); grounding (numbers only from the snapshot or a tool); actions (preview → code → confirm; state price and pay-from before asking for the code; never claim success before the tool returns success; after a write use the tool's figures, not the snapshot); security (never ask for PIN/password, never repeat a code aloud, only the logged-in account); playbooks (recharge not credited → lookup_transactions then case; unexpected deduction → explain_deductions; slow data → check_network_status then case; pack not activated → lookup_transactions then case); escalation (anger, repeated failure, asks for a human, or no tool fits → request_human_agent); keep the politics/religion and confidentiality hard rules. Keep the existing Bangla phrasing guidance that still applies (polite forms, চাচ্ছেন, করবো?, কোনো/কোন spelling); drop everything about listings, viewings, areas covered, lakh/crore.
  `KNOWLEDGE_SCOPE_DEFAULT` / `KNOWLEDGE_SCOPE_RAG` / `_CONTACT_FALLBACK`: unknown policy details → hotline `{operator_phone}` or `{operator_address}`; RAG variant calls `search_knowledge_base` first for policies, terms, rollover, SIM replacement, roaming, coverage.
  `DEFAULT_GREETING_INBOUND`, `DEFAULT_GREETING_NUDGE` (mentions `{nudge_text}`), `SPOKEN_GREETINGS_INBOUND` (3 Bangla lines with `{customer_name}`), `SPOKEN_GREETINGS_GUEST` (2 lines). Delete the cold-call / follow-up constants.

- [ ] **Step 1: Write failing tests:**

```python
def test_snapshot_for_prepaid_persona(bss_world): ...    # balance, pack data left, expiry day, masked number, incident line
def test_snapshot_for_postpaid_shows_due(bss_world): ...
def test_unknown_subscriber_becomes_guest(): ...         # random uuid -> subscriber_id None, GUEST_SNAPSHOT
def test_nudge_text_only_for_own_notification(bss_world): ...
_REAL_ESTATE = ("apartment", "listing", "property", "viewing", "realty", "agency", "lakh", "flat", "ফ্ল্যাট", "ভিউয়িং")
def test_prompts_have_no_real_estate_words(): ...        # system prompt (rag on/off), all greeting defaults, KB tool description
def test_prompt_mentions_only_registered_tools(): ...    # every tool name appearing in the prompt is in _session_tools
def test_prompt_rules_present(): ...                     # "never repeat" code rule, "PIN", "request_human_agent", snapshot appended
def test_greeting_uses_nudge_when_present(): ...         # fake session: generate_reply instructions contain nudge_text
def test_guest_greeting_is_canned_without_name(): ...
```
Update `tests/test_prompts.py::test_unknown_details_point_to_the_agency_contact` to the operator hotline/address and the new fallback copy.

- [ ] **Step 2: Run** `uv run pytest tests/test_snapshot.py tests/test_prompts.py tests/test_greeting_guard.py -q` — expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [ ] **Step 5: Commit** `feat(agent): telco system prompt, account snapshot and greetings`.

---

### Task 9: Internal LLM prompts → telco

Carry-overs: turn_judge `search_context` dead; quick_reply pending-action gate; `ChannelLiteral` still allows `"outbound_coldcall"`.

**Files:**
- Modify: `app/agent/turn_router.py`, `app/agent/turn_judge.py`, `app/agent/prefetch.py`, `app/agent/gated_agent.py:157`, `app/agent/quick_reply.py` (`FAST_RULES`, `_FILLER_SYSTEM`, `route`), `app/services/voice_preview.py` (`_SAMPLES`), `app/api/routes_conversations.py:28`
- Test: `tests/test_turn_router.py`, `tests/test_turn_judge.py`, `tests/test_prefetch.py`, `tests/test_quick_reply.py`, `tests/test_voice_preview.py`, `tests/test_conversations_api.py`

**Interfaces:**
- Produces:
  - `RouterArgs(packages: dict, knowledge_query: str | None)`; schema `{"packages": {kind, max_price, min_data_gb, validity_days}, "knowledge_query"}` (all nullable; kind enum data/voice/bundle/sms). `build_request(model, history, utterance, reasoning_effort="none")` — the `last_search` / `shown_listings` parameters go.
  - Jev lookup choices: `packages` (asks what packs exist / gives pack criteria), `knowledge_base`, `none` (account questions answered from the snapshot or tools the LLM calls itself, writes, codes, greetings). `build_state` / `build_request` lose `search_context`; `search_context()` deleted.
  - `prefetch._LOOKUP_TOOLS = {"packages": ("search_packages",), "knowledge_base": (search_knowledge_base.TOOL_NAME,)}`; `packages` runs `search_packages_text` in `run_db`.
  - `quick_reply.route` returns `None` whenever `userdata.pending_action` or `userdata.pending_case` is set. `FAST_RULES` hands off for any balance/pack/usage/price/offer/policy fact, any purchase/recharge/redeem/case request, any 4–8 digit code, and a complaint. Filler examples become telco ("ব্যালেন্সটা চেক করছি।", "প্যাকগুলো দেখছি।", "Checking your account.").
  - `voice_preview._SAMPLES` telco lines with `{agent_name}` / `{operator_name}`, numbers spelled out.
  - `ChannelLiteral = Literal["inbound_chat"]`.

- [ ] **Step 1: Update/write failing tests:** router parse of a packages payload (nulls dropped); Jev request has no `search_context`, lookup criteria keys `{"packages", "knowledge_base", "none"}` (`knowledge_base` dropped when RAG off); prefetch of `packages` injects a `search_packages` call + output; `quick_reply.route` returns `None` with a pending action even when Jev says `none` at p=0.99; filler/fast prompts contain none of the `_REAL_ESTATE` words from Task 8; conversations API rejects `channel=outbound_coldcall` with 422.
- [ ] **Step 2: Run** those test files — expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — expect PASS.
- [ ] **Step 5: Commit** `feat(agent): telco turn router, judge, quick replies and voice preview`.

---

### Task 10: KB seed documents

**Files:**
- Create: `app/data/kb/package-terms.md`, `recharge-refund-policy.md`, `data-rollover.md`, `sim-replacement.md`, `roaming-faq.md`, `coverage-notes.md`; `app/data/seed_kb.py`
- Modify: `app/data/seed_all.py`
- Test: `tests/test_seed_kb.py`

**Interfaces:**
- Produces: `seed_kb(db: Session) -> int` — for each `kb/*.md` without a `RagSource` of the same name (`"telco KB: <stem>"`), `rag_service.create_text_source(db, name=..., text=...)`; sets `agent_config.rag_enabled = True`; returns sources created. Idempotent. `seed_all` calls it after `seed_telco` (also with `--reset`; it never deletes KB sources).
- Docs: each has an English section then a Bangla section; facts must agree with `seed_telco` (package names/prices/validity, recharge limits ৳20–1000 / ৳5000 per day, 10% cashback on ৳200+, 700 points for 1 GB, hotline = `operator_phone` default). 150–400 words each.

- [ ] **Step 1: Write failing tests:** `seed_kb` creates 6 sources and pending ingest jobs on a clean DB (delete prior `telco KB:` sources in the fixture), a second run creates 0, `rag_enabled` is true; every doc contains both Bengali script and Latin text; `package-terms.md` mentions every active seed package code.
- [ ] **Step 2: Run** `uv run pytest tests/test_seed_kb.py -q` — expect FAIL.
- [ ] **Step 3: Write the docs and `seed_kb`.**
- [ ] **Step 4: Run** `uv run pytest -q` — expect PASS; then `uv run python -m app.data.seed_all` twice — second run reports 0 KB sources created.
- [ ] **Step 5: Commit** `feat(data): telco knowledge base seed documents`.

---

### Task 11: Conversation eval set

**Files:**
- Rewrite: `scripts/router_bench/cases.json`; modify `scripts/router_bench/run.py` (new `RouterArgs` shape: compare `packages` args), `scripts/judge_bench/cases.json` (telco wording for histories and utterances)
- Create: `tests/test_router_bench_cases.py`

**Interfaces:**
- Consumes: Task 9 `turn_router.build_request` / `RouterArgs` / lookup choices.
- Cases: 25 utterances — at least 8 Bangla, 8 English, 6 Banglish — each with `history`, `utterance`, `lookup` ∈ {packages, knowledge_base, none}, optional `packages` args and an `expected_tool` (the tool the main LLM should call, e.g. `get_account_summary`, `start_recharge`, `verify_otp`, `request_human_agent`, or `null`). Cover every tool group in spec 4.1 at least once.

- [ ] **Step 1: Write failing test:** loads both cases files; every `lookup` is valid; every `packages` key is in the router schema; every `expected_tool` is a registered telco tool name, `search_knowledge_base`, or null; language counts as above; no `_REAL_ESTATE` words.
- [ ] **Step 2: Run** `uv run pytest tests/test_router_bench_cases.py -q` — expect FAIL.
- [ ] **Step 3: Write the cases; update `run.py`** to the new shape (reports lookup accuracy and package-arg accuracy; `expected_tool` is printed for manual review).
- [ ] **Step 4: Run** the test — PASS. With an OpenRouter key: `cd backend && uv run python ../scripts/router_bench/run.py --models openai/gpt-5.4-nano` (manual; record the accuracy in the commit message, or "not run: no key").
- [ ] **Step 5: Commit** `test(agent): telco router eval cases`.

---

### Task 12: Phase verification

- [ ] **Step 1:** `uv run pytest -q` — all pass; `uv run alembic check` — clean.
- [ ] **Step 2:** `grep -rniE "apartment|listing|realty|viewing|booking|lakh" app/ --include=*.py` — only hits that are not real-estate meaning (justify each in the commit body) or none.
- [ ] **Step 3:** Fresh DB (the telco migration is one-way, so use a scratch database): `docker exec telco-pg createdb -U telco telco_fresh`, then with `DATABASE_URL=postgresql+psycopg://telco:telco@localhost:5435/telco_fresh` run `uv run alembic upgrade head && uv run python -m app.data.seed_all` — succeeds; then `docker exec telco-pg dropdb -U telco telco_fresh`.
- [ ] **Step 4:** Update `README.md` agent section (tool list, OTP demo flow, `OPERATOR_*` env vars) and the memory carry-over file (strike Phase 2 items done).
- [ ] **Step 5: Commit** `docs: phase 2 agent notes`.
