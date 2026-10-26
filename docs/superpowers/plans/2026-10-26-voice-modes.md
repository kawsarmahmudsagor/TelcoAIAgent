# Voice Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guests chat in text only. Logged-in customers can speak, and get voice or text replies
depending on a new dashboard switch, **Voice responses**.

**Architecture:** Every browser session is still built with STT and TTS. Right after
`session.start`, the agent picks a `VoiceMode` (`off` / `text_reply` / `full`). It switches
livekit's runtime audio input and output to match, appends a CHANNEL note to the prompt in the
text modes, and publishes a `voice` participant attribute for the UI. A guest who logs in
mid-chat is re-applied by `AccountLink`.

**Tech Stack:**
- Backend: FastAPI, SQLAlchemy, Alembic, livekit-agents 1.7, pytest.
- Frontend: Next.js, `@livekit/components-react`.

**Spec:** `docs/superpowers/specs/2026-10-26-voice-modes-design.md`

## Global Constraints

- Config column `voice_replies_enabled`: Boolean, `default=True`, `server_default="true"`.
- `VoiceMode` values are exactly `"off"`, `"text_reply"` and `"full"`.
- The participant attribute key is `"voice"`. Backend `VOICE_ATTRIBUTE` and frontend
  `VOICE_ATTRIBUTE` must match.
- `CHANNEL_TEXT_NOTE` text, verbatim: `CHANNEL — your replies are shown as text, not spoken. Keep the same short style. Offer to show more, not to read out more.`
- Dashboard switch label: `Voice responses`. Description, verbatim: `Off: logged-in customers can still speak; the assistant replies in text. Guests always chat in text. Applies to new chats.`
- The phone path (`userdata.is_phone_call`) is always `full`, and `apply` is never called for it.
- Config is read once at session start. Never re-read it on upgrade.
- Backend tests: `cd backend && uv run --extra dev pytest -q`.
- Frontend checks: `cd frontend && pnpm -s typecheck && pnpm -s lint`.

## Review Focus

1. **A guest publishes a mic track anyway.** No STT may run. Task 2's apply test asserts
   `input.set_audio_enabled(False)` for a guest.
2. **A guest logs in while Voice responses is OFF.** The mode must become `text_reply` and the
   CHANNEL note must stay, appearing only once. Task 3 has a test.
3. **`apply` raises during an upgrade.** The account link still succeeds, and the session stays
   text-only. Task 3 has a test.
4. **The UI before the agent has published `voice`.** A signed-out visitor must never see a mic
   button flash. Task 5's `useVoiceMode` falls back to `useSignedIn()`; check it manually in
   Task 5.
5. **A snapshot refresh after the note is added.** `snapshot_refresh`'s `str.replace` of the
   snapshot block must still find it. Task 2 has a test: the snapshot is replaceable when the
   note is present.

---

### Task 1: `voice_replies_enabled` config field

**Files:**
- Modify: `backend/app/models/agent_config.py`. Add the column near `quick_reply_enabled`.
- Create: `backend/migrations/versions/e5b9c3d72a14_agent_voice_replies.py`. Its down_revision
  is the current head, `d2e8b4a61f07`.
- Modify: `backend/app/services/agent_config_service.py`. Add the field to `ResolvedAgentConfig`
  with default `True`, and resolve it from the row with `bool(row.voice_replies_enabled)`.
- Modify: `backend/app/schemas/agent_config.py`. The read schema gets `voice_replies_enabled: bool`.
  The update schema gets `voice_replies_enabled: bool | None = None`.
- Modify: `backend/app/api/routes_agent_config.py`. Add the field to the updatable field list
  (next to `"quick_reply_enabled"`) and to the response mapping.
- Test: `backend/tests/test_agent_config.py`

**Interfaces:**
- Produces: `ResolvedAgentConfig.voice_replies_enabled: bool`, plus the API field
  `voice_replies_enabled` on GET and PATCH of the agent config route.

- [ ] **Step 1: Write failing tests.** Follow the file's existing quick-reply round-trip test.
  - `test_voice_replies_default_true`: a GET of the config returns `voice_replies_enabled is True`.
    `agent_config_service.load().voice_replies_enabled is True`.
  - `test_voice_replies_round_trip`: an update to `false` reads back as `False` from both the
    API and `load()`. Restore it to `true` at the end.
- [ ] **Step 2:** Run `uv run --extra dev pytest -q tests/test_agent_config.py -k voice_replies`.
  Expected: FAIL.
- [ ] **Step 3:** Implement the five file changes above.
- [ ] **Step 4:** Run `uv run --extra dev alembic upgrade head`, then
  `uv run --extra dev alembic check`. Expected: "No new upgrade operations detected." The
  Step 2 tests should now PASS.
- [ ] **Step 5: Commit** `feat(config): voice_replies_enabled agent setting`.

---

### Task 2: `voice_mode` module and the CHANNEL note

**Files:**
- Create: `backend/app/agent/voice_mode.py`
- Modify: `backend/app/agent/userdata.py`. Add `voice_mode: "VoiceMode | None" = None` to
  `SessionUserdata`.
- Modify: `backend/app/agent/prompt_defaults.py`. Add the `CHANNEL_TEXT_NOTE` constant (exact
  text in Global Constraints).
- Modify: `backend/app/agent/persona.py`. `build_system_prompt` appends
  `channel_note(mode_for(userdata, config))` as the last block, after `_BROWSER_END_NOTE`,
  separated by `\n\n`, and only when the note is non-empty.
- Test: `backend/tests/test_voice_mode.py`

**Interfaces:**
- Consumes: `ResolvedAgentConfig.voice_replies_enabled` (Task 1).
- Produces:
  - `class VoiceMode(str, Enum)` with members `off`, `text_reply` and `full`.
  - `VOICE_ATTRIBUTE = "voice"`.
  - `mode_for(userdata: SessionUserdata, config: ResolvedAgentConfig) -> VoiceMode`. A phone
    call gives `full`. No `subscriber_id` gives `off`. Otherwise it gives `full` if
    `config.voice_replies_enabled`, else `text_reply`.
  - `channel_note(mode: VoiceMode) -> str`. It returns `""` for `full`, else `CHANNEL_TEXT_NOTE`.
  - `async apply(session: AgentSession, agent: Agent, userdata: SessionUserdata, config: ResolvedAgentConfig, room: rtc.Room) -> VoiceMode`. In order:
    1. Compute the mode.
    2. `session.input.set_audio_enabled(mode != off)`.
    3. `session.output.set_audio_enabled(mode == full)`.
    4. If the note for the old mode (`userdata.voice_mode`, or the mode the prompt was built
       with when that is `None`, i.e. from `CHANNEL_TEXT_NOTE in agent.instructions`) differs
       from the note for the new mode, call `agent.update_instructions(...)`. It appends the
       note with `\n\n` or removes `\n\n` + note.
    5. Set `userdata.voice_mode = mode`.
    6. `await room.local_participant.set_attributes({VOICE_ATTRIBUTE: mode.value})`.

- [ ] **Step 1: Write failing tests** in `test_voice_mode.py`.
  - Fakes: reuse the `FakeRoom`/`FakeAgent` shape from `tests/test_account_link.py`. Add a
    `FakeSession` whose `input` and `output` each record `set_audio_enabled` calls.
  - `test_mode_for_table`: parametrize over (guest, logged in) × `voice_replies_enabled`
    (True, False), plus a phone call. Expected:
    - guest → `off`, for both config values;
    - logged in with True → `full`;
    - logged in with False → `text_reply`;
    - phone call → `full`.
  - `test_apply_guest_disables_both_and_publishes_off`: input `[False]`, output `[False]`,
    attributes `{"voice": "off"}`.
  - `test_apply_full_enables_both`: logged in with config True gives input `[True]` and output
    `[True]`.
  - `test_apply_text_reply`: input `[True]`, output `[False]`, attribute `"text_reply"`.
  - `test_apply_removes_note_going_to_full`:
    - Setup: instructions contain `"\n\n" + CHANNEL_TEXT_NOTE` and `userdata.voice_mode = off`.
      The user is logged in with config True.
    - Expect: the note is gone after `apply`.
  - `test_apply_keeps_single_note_going_to_text_reply`: going from `off` to `text_reply`, the
    instructions are unchanged and contain the note exactly once.
  - `test_prompt_has_note_only_in_text_modes`: `build_system_prompt` contains
    `CHANNEL_TEXT_NOTE` for a guest and for `text_reply`, and not for `full`.
  - `test_snapshot_replaceable_with_note`: for a guest prompt, `GUEST_SNAPSHOT in prompt` and
    `prompt.replace(GUEST_SNAPSHOT, "X", 1)` still contains the note.
- [ ] **Step 2:** Run `uv run --extra dev pytest -q tests/test_voice_mode.py`. Expected: FAIL
  (ImportError).
- [ ] **Step 3:** Implement the four file changes.
- [ ] **Step 4:** Run `uv run --extra dev pytest -q tests/test_voice_mode.py tests/test_prompts.py`.
  Expected: PASS. If a `test_prompts.py` assertion pins the exact prompt ending for a guest,
  update it to expect the note.
- [ ] **Step 5: Commit** `feat(agent): voice modes and text-channel prompt note`.

---

### Task 3: Wire `apply` into session start and the guest upgrade

**Files:**
- Modify: `backend/app/agent/entrypoint.py`.
  - In `entrypoint`, call `voice_mode.apply(session, agent, userdata, config, ctx.room)`
    immediately after `await session.start(...)`, before `ActionRpc`.
  - On any exception: log it, then `session.input.set_audio_enabled(False)` and
    `session.output.set_audio_enabled(False)`.
- Modify: `backend/app/agent/account_link.py`.
  - `AccountLink.__init__` gains a keyword `config: ResolvedAgentConfig`.
  - In `link()`, after `publish_account(...)` and before `generate_reply(LOGIN_FOLLOWUP)`, call
    `await voice_mode.apply(...)` wrapped in try/except. On failure, log it with
    `logger.exception`, and the link still returns True.
  - `entrypoint` passes `config=config` when it constructs `AccountLink`.
- Test: `backend/tests/test_account_link.py`

**Interfaces:**
- Consumes: `voice_mode.apply` (Task 2).
- Produces: `AccountLink(*, session, agent, userdata, room, config)`.

- [ ] **Step 1: Write failing tests.** Update `_link()` in `test_account_link.py` to pass a
  config and give `FakeSession` `input`/`output` recorders (as in Task 2).
  - `test_upgrade_turns_voice_on`: a guest with `voice_mode=off` and config True links. Expect
    `userdata.voice_mode == full`, room attribute `voice == "full"`, and the note removed from
    instructions.
  - `test_upgrade_with_voice_replies_off`: config False gives `text_reply`. Input is enabled,
    output disabled, and the note appears exactly once.
  - `test_upgrade_survives_apply_failure`: monkeypatch `voice_mode.apply` to raise. `link()`
    still returns True, and `userdata.subscriber_id` is set.
  - The existing tests in the file must still pass with the new `config` argument.
- [ ] **Step 2:** Run `uv run --extra dev pytest -q tests/test_account_link.py`. Expected: the
  new tests FAIL.
- [ ] **Step 3:** Implement the changes in the two files.
- [ ] **Step 4:** Run the full suite, `uv run --extra dev pytest -q -p no:warnings`. Expected:
  all pass (1 skipped, R7).
- [ ] **Step 5: Commit** `feat(agent): apply voice mode at start and on guest login`.

---

### Task 4: Dashboard "Voice responses" switch

**Files:**
- Modify: `frontend/lib/types/agent-config.ts`. Add `voice_replies_enabled: boolean` to the
  config type and `voice_replies_enabled?: boolean | null` to the update type, mirroring
  `quick_reply_enabled`.
- Modify: `frontend/components/dashboard/chatbot/config-draft.ts`. Add the field to the draft
  type, the field→tab map (the same tab as `voice-section`'s other fields), and the
  config→draft mapping.
- Modify: `frontend/components/dashboard/chatbot/voice-section.tsx`. Add a `SwitchRow` at the
  top with the label and description from Global Constraints, bound to
  `draft.voice_replies_enabled`.

**Interfaces:**
- Consumes: the API field `voice_replies_enabled` (Task 1).

- [ ] **Step 1:** Make the three edits.
- [ ] **Step 2:** Run `pnpm -s typecheck && pnpm -s lint`. Expected: clean.
- [ ] **Step 3: Commit** `feat(dashboard): Voice responses switch`.

---

### Task 5: Customer UI follows the voice mode

**Files:**
- Create: `frontend/components/customer/use-voice-mode.ts`
- Modify: `frontend/components/portal/assistant/assistant-provider.tsx`. In `AssistantSession`:
  - call `useMicOnConnect(voiceRequested && mode !== 'off')`;
  - `toggleMic` returns early when `mode === 'off'`;
  - expose `voiceMode: VoiceMode` on the assistant context value.
- Modify: `frontend/components/portal/assistant/assistant-chat.tsx`. Render the
  `EmptyState` "Talk instead of typing" button and the `Composer` mic button only when
  `voiceMode !== 'off'`.

**Interfaces:**
- Consumes: the `voice` agent attribute (Task 3); `useAgentAttribute` from
  `@/lib/livekit-text-streams`; `useSignedIn` from `@/components/customer/customer-assistant`.
- Produces:
  - `export type VoiceMode = 'off' | 'text_reply' | 'full'`.
  - `export const VOICE_ATTRIBUTE = 'voice'`, with a comment pointing at the backend constant.
  - `export function useVoiceMode(): VoiceMode`. It returns the attribute when it is one of the
    three values. Otherwise `useSignedIn()` decides: a signed-in customer gives `'full'`, and
    `null` or `undefined` gives `'off'`.

- [ ] **Step 1:** Create the hook and make the two component edits.
- [ ] **Step 2:** Run `pnpm -s typecheck && pnpm -s lint`. Expected: clean.
- [ ] **Step 3: Manual check.** It needs FastAPI, the agent worker and a reachable `LIVEKIT_URL`.
  1. Signed out, on the home page: no mic button appears, even before connecting. A typed
     question gets a text reply.
  2. Log in from the same tab: the mic button appears and the chat carries on.
  3. With Voice responses ON: speak, and the reply is audible.
  4. Turn it OFF in `/dashboard/chatbot`, then start a new chat: speak, and the reply and any
     filler show as text with no audio.

  If LiveKit isn't reachable, record the skip in the final report. Do not claim the check passed.
- [ ] **Step 4: Commit** `feat(portal): hide voice for guests; follow the agent's voice mode`.
