# Reply Language Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A browser chat starts with an English / বাংলা pick, and the bot replies only in that language for the whole chat.

**Architecture:** The pick rides the existing token metadata path (`participant_attributes` → token route → dispatch metadata → `userdata`) and is stored on the conversation row. One backend module, `app/agent/reply_language.py`, is the only place that turns the pick into wording. Every per-turn language guess (prompt, per-turn reminder, fillers, idle lines, other-language line, number speech) defers to it when set and is unchanged when unset.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, LiveKit Agents (Python), pytest; Next.js 15, React 19, TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-30-reply-language-picker-design.md`

## Global Constraints

- Values are exactly `"en"` and `"bn"`. Anything else, or missing, means unset (`None` / `null`) and today's behaviour.
- Phone calls never get a pick.
- STT, the turn gate's language checks and the dashboard STT language setting do not change.
- `CHANNEL_TEXT_NOTE` stays the last block of the system prompt.
- The brand is written `telco`, never `telco.`. The bot says package/প্যাকেজ, never pack.
- Bangla copy is modern spoken Bangla in the respectful আপনি form.
- Full `pytest` wipes and reseeds the dev KB: re-embed after a full run.
- The agent worker runs in `start` mode: restart it before any manual test.

## Review Focus

1. Resuming a pre-feature chat (stored `reply_language` is null): the picker shows, and the pick is saved onto that row on reopen. Test in Task 2.
2. A customer picks English and only ever writes Bangla. Every reply, filler, idle line and goodbye is English. The prompt, reminder and filler tests in Tasks 3–5 pin each path; the manual check in Task 8 covers the main model.
3. A nudge click or `?q=` send before any pick: the panel opens on the picker, and the start runs after the pick, with the pick in its token. Manual check in Task 7.
4. Token tampering (`reply_language: "fr"` or `["en"]`): dropped, so the chat is unset rather than broken. Test in Task 6.
5. A guest logs in mid-chat (`account_link` rebuilds the prompt): the language block survives. Test in Task 3.

---

### Task 1: Pick parsing and userdata

**Files:**
- Create: `backend/app/agent/reply_language.py`
- Modify: `backend/app/agent/userdata.py` (new field next to `text_start`), `backend/app/agent/session_context.py:21-29`
- Test: `backend/tests/test_reply_language.py`, `backend/tests/test_session_context.py`

**Interfaces:**
- Produces:
  - `ReplyLanguage = Literal["en", "bn"]`
  - `parse(raw: object) -> ReplyLanguage | None`
  - `fixed(userdata: object) -> ReplyLanguage | None`, which reads `getattr(userdata, "reply_language", None)`
  - `name(lang: ReplyLanguage) -> str`, giving `"English"` or `"Bangla (Bengali script)"`
  - `in_language(lang: ReplyLanguage | None, default: str) -> str`, giving `f"in {name(lang)}"` when set, else `default`
  - `SessionUserdata.reply_language: ReplyLanguage | None = None`

- [ ] **Step 1: Write failing tests.**
  - `test_parse`: `parse("en") == "en"`, `parse("bn") == "bn"`, and `parse` gives `None` for `"EN"`, `"fr"`, `["en"]`, `None` and `""`.
  - `test_in_language`: `in_language("en", "X") == "in English"` and `in_language(None, "X") == "X"`.
  - In `test_session_context.py`: metadata `{"reply_language": "bn"}` resolves to `userdata.reply_language == "bn"`; `{"reply_language": "xx"}` resolves to `None`.
- [ ] **Step 2:** Run `uv run pytest tests/test_reply_language.py tests/test_session_context.py -q`. Expect FAIL (no module).
- [ ] **Step 3:** Implement the module and the field. Set `reply_language=parse(meta.get("reply_language"))` in `resolve`.
- [ ] **Step 4:** Rerun the command. Expect PASS.
- [ ] **Step 5:** Commit `feat(agent): reply language pick parsed into session userdata`.

### Task 2: Store on the conversation, keep on resume, return in history

**Files:**
- Modify:
  - `backend/app/models/conversation.py`: `reply_language: Mapped[str | None] = mapped_column(String(2), nullable=True)`
  - `backend/app/repositories/conversation_repo.py`: `create(..., reply_language=None)`; `reopen(..., reply_language=None)` fills the column only where it is null
  - `backend/app/agent/transcript.py`: `create_conversation`, `load_resume_history`, `_reopen_conversation`
  - `backend/app/schemas/conversation.py`: `reply_language: str | None` on `VisitorConversationSummary` and `VisitorConversationDetail`
  - `backend/app/api/routes_public_conversations.py`: fill the new field
- Create: a migration in `backend/migrations/versions/` adding the nullable column (autogenerate, then check it only adds this column)
- Test: `backend/tests/test_transcript.py`, `backend/tests/test_public_conversations.py`

**Interfaces:**
- Consumes `reply_language.parse` and `SessionUserdata.reply_language`.
- Produces: `load_resume_history` sets `userdata.reply_language = parse(conversation.reply_language)` when the stored value is not null. The stored value beats the metadata value. The history JSON gains `reply_language`.

- [ ] **Step 1: Write failing tests.**
  - `test_create_conversation_stores_reply_language`: the row's `reply_language == "en"`.
  - `test_resume_keeps_stored_language`: stored `"bn"` and metadata `"en"` give `userdata.reply_language == "bn"` after `load_resume_history`.
  - `test_resume_legacy_row_takes_pick`: stored null and metadata `"en"` give userdata `"en"`; after reopen the row is `"en"`.
  - `test_history_returns_reply_language`: the list and detail responses include `"reply_language": "bn"`.
- [ ] **Step 2:** Run `uv run pytest tests/test_transcript.py tests/test_public_conversations.py -q`. Expect FAIL.
- [ ] **Step 3:** Implement the column, migration, repo, transcript and schema changes. Run `uv run alembic upgrade head`.
- [ ] **Step 4:** Rerun the command. Expect PASS.
- [ ] **Step 5:** Commit `feat(conversations): store each chat's reply language and keep it on resume`.

### Task 3: Prompt block and language-specific notes

**Files:**
- Modify:
  - `backend/app/agent/reply_language.py`: `prompt_block`
  - `backend/app/agent/persona.py`: append the block in `build_system_prompt`, before the channel note; the `_TEXT_START_NOTE` and `_BROWSER_END_NOTE` phrases
  - `backend/app/agent/entrypoint.py:455-466`: the goodbye texts become functions of the language
- Test: `backend/tests/test_prompts.py`, `backend/tests/test_account_link.py`

**Interfaces:**
- Produces:
  - `prompt_block(lang: ReplyLanguage) -> str`
  - `end_call_goodbye(lang: ReplyLanguage | None) -> str` and `browser_end_goodbye(lang: ReplyLanguage | None) -> str` in `entrypoint.py`, replacing `_END_CALL_GOODBYE` and `_BROWSER_END_GOODBYE` at lines 531 and 540
- `prompt_block` copy, exact (with `{L}` = `name(lang)`):
  ```
  REPLY LANGUAGE — the customer chose {L} for this chat. Reply only in {L}, in every reply,
  whatever language the customer writes or speaks in (English, Bangla or Banglish), including
  their very first message, and whatever language a tool or the knowledge base returns. Greet in
  {L}. This overrides the LANGUAGE rules above and any note that says to use the language of the
  customer's message. For speech you cannot make out, or another language, say exactly
  "{OTHER_LANGUAGE_LINE for lang}" and nothing else.
  ```
  For `"bn"`, add after the first sentence: `Write Bangla in Bengali script, never in English letters.`
- The notes use `in_language(lang, "in the language of their message")` and its siblings, so unset gives the exact text used today.

- [ ] **Step 1: Write failing tests.**
  - `test_prompt_fixed_english`: the prompt contains `"REPLY LANGUAGE"` and `"Reply only in English"`, and `CHANNEL_TEXT_NOTE` (text-reply mode) still ends it.
  - `test_prompt_unset_unchanged`: with `reply_language=None` the prompt equals today's (no `"REPLY LANGUAGE"`).
  - `test_text_start_note_follows_pick`: `"in English"` is present and the latest-message wording is absent.
  - `test_goodbye_texts`: `browser_end_goodbye("bn")` contains `"in Bangla"`; `browser_end_goodbye(None)` equals the old constant.
  - In `test_account_link.py`: after the guest-to-customer prompt rebuild, the block is still there.
- [ ] **Step 2:** Run `uv run pytest tests/test_prompts.py tests/test_account_link.py tests/test_browser_end_call.py -q`. Expect FAIL.
- [ ] **Step 3:** Implement. The block needs `OTHER_LANGUAGE_LINES` from Task 5. Define `OTHER_LANGUAGE_LINES` in `reply_language.py` now, so Task 5 only wires it in.
  - `"en"`: `"I could not understand that. Could you kindly repeat that?"`
  - `"bn"`: `"দুঃখিত, বুঝতে পারিনি। আরেকবার বলবেন, প্লিজ?"`
- [ ] **Step 4:** Rerun the command. Expect PASS.
- [ ] **Step 5:** Commit `feat(agent): prompt and goodbye notes follow the chosen reply language`.

### Task 4: Per-turn reminder

**Files:**
- Modify: `backend/app/agent/closing_offer.py` (`reminder`, `WRAP_UP_REMINDER`, `BACKSTOP_REMINDER`)
- Test: `backend/tests/test_closing_offer.py`

**Interfaces:**
- `reminder(chat_ctx, userdata) -> str | None` keeps its signature:
  - Unset: today's results, unchanged.
  - Set: never `None`. It returns the wrap-up or backstop text with `in_language(lang, "in the language of their message")`, followed by `f" Reply in {name(lang)}."`. With no reminder due, or while an action or case is pending, it returns `f"Reply in {name(lang)}, whatever language the customer used."`

- [ ] **Step 1: Write failing tests.**
  - `test_reminder_language_only`: lang `"en"` and nothing due gives `"Reply in English, whatever language the customer used."`
  - `test_reminder_wrap_up_with_language`: with `wrap_up` set, the text contains `"in English"` and not `"language of their message"`.
  - `test_reminder_pending_action_still_language`: with lang `"bn"` and a pending action, the result has `"Reply in Bangla"`.
  - `test_reminder_unset_unchanged`: today's three cases unchanged.
- [ ] **Step 2:** Run `uv run pytest tests/test_closing_offer.py -q`. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun the command. Expect PASS.
- [ ] **Step 5:** Commit `feat(agent): per-turn reply language reminder`.

### Task 5: Fillers, idle lines, other-language line, number speech

**Files:**
- Modify:
  - `backend/app/agent/quick_reply.py`: `fast_filler`, `build_filler_request`, `compose_filler`, `QuickReplyRuntime`, `avoid`
  - `backend/app/agent/entrypoint.py`: `QuickReplyRuntime(...)` at line 742, and `tts_text_transforms` at line 689
  - `backend/app/agent/idle_checkin.py`: `_reply_language` and its callers
  - `backend/app/agent/gated_agent.py:79,849`
  - `backend/app/agent/speech_numbers.py`
- Test: `backend/tests/test_quick_reply.py`, `backend/tests/test_idle_checkin.py`, `backend/tests/test_gated_session.py`, `backend/tests/test_speech_numbers.py`

**Interfaces:**
- `fast_filler(..., language: ReplyLanguage | None = None)`:
  - When set, `bangla = language == "bn"` replaces `_speaks_bangla`.
  - Template candidates whose `turn_gate.classify_script(line)` is a different script from the pick are dropped. `"none"` script counts as matching.
- `compose_filler(..., language=None)` and `build_filler_request(..., language=None)`: when set, the user message ends with `f"LANGUAGE: write the line in {name(language)}, whatever language the customer used."`
- `QuickReplyRuntime(..., language: ReplyLanguage | None = None)` passes it to both. `avoid()` keeps lines in the pick's script when set.
- `idle_checkin._reply_language(session, language=None)` returns `language` when set. Callers pass `fixed(userdata)`.
- `gated_agent` says `OTHER_LANGUAGE_LINES[fixed(userdata) or "en"]`.
- `speech_numbers.number_speaker(language: ReplyLanguage | None) -> Callable[[AsyncIterable[str]], AsyncIterable[str]]`:
  - When set, numbers are converted in that language with no holdback wait.
  - `speak_numbers_as_words` stays as `number_speaker(None)`.
  - The entrypoint uses `number_speaker(fixed(userdata))`.

- [ ] **Step 1: Write failing tests.**
  - `test_fast_filler_fixed_english_on_bangla_utterance`: utterance `"আমার ব্যালেন্স কত?"` with `language="en"` gives a line whose script is `"en"`.
  - `test_fast_filler_fixed_bangla_on_english_utterance`: the reverse case gives `"bn"`.
  - `test_filler_request_language_line`: the payload's last user content ends with the `LANGUAGE:` sentence.
  - `test_idle_lines_follow_pick`: a last assistant reply in Bangla with pick `"en"` gives the English check-in and goodbye.
  - `test_other_language_line_bangla`: a gated session with pick `"bn"` says the Bangla line.
  - `test_number_speaker_fixed_bn`: `"৳300"` streamed with `"bn"` gives Bangla words, even though the text has no Bengali letters.
  - All existing tests in these files still pass, so unset behaviour is unchanged.
- [ ] **Step 2:** Run `uv run pytest tests/test_quick_reply.py tests/test_idle_checkin.py tests/test_gated_session.py tests/test_speech_numbers.py -q`. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun the command. Expect PASS.
- [ ] **Step 5:** Commit `feat(agent): fillers, idle lines, numbers and other-language line follow the pick`.

### Task 6: Frontend plumbing

**Files:**
- Modify:
  - `frontend/lib/agent-dispatch.ts`: `extras.replyLanguage?: unknown`, emitted only when it is exactly `'en'` or `'bn'`
  - `frontend/app/api/token/route.ts:78-83`: `replyLanguage: body?.participant_attributes?.reply_language`
  - `frontend/lib/visitor-id.ts`: `useVisitorSessionOptions(..., replyLanguage: ReplyLanguage | null = null)` adds `reply_language`
  - `frontend/components/chat-bubble/chat-bubble-context.tsx`: state and gating
  - `frontend/components/portal/assistant/assistant-provider.tsx:281`: resume sets the language
  - the history types file that holds the conversation detail type
- Test: the existing frontend test for `agent-dispatch` if one exists (`grep -rl buildDispatchMetadata frontend --include=*.test.*`); otherwise add `frontend/lib/agent-dispatch.test.ts` in the repo's test runner style. If there is no runner, typecheck only.

**Interfaces:**
- Produces:
  - `export type ReplyLanguage = 'en' | 'bn'` in `frontend/lib/reply-language.ts`.
  - On `ChatBubbleContextValue`: `replyLanguage: ReplyLanguage | null`, `chooseReplyLanguage(lang: ReplyLanguage): void`, `languagePending: boolean`.
  - `ResumedConversation` gains `replyLanguage: ReplyLanguage | null`.
- Gating rule in `startSession`:
  - With `replyLanguage === null` and not resuming a stored-language chat, store the call as a deferred start and return its promise. Set `languagePending = true` and open the panel.
  - `chooseReplyLanguage` sets the language and then runs the deferred start, using the same deferral pattern as `textStart` (wait for the options to re-render).
  - The nudge path (`startNudgeSession`) goes through the same gate.
- Reset `replyLanguage` to `null` when the session disconnects after having connected, and when `setResumed(null)` starts a new chat.
- Resume: `setResumed({ id, messages, replyLanguage: detail.reply_language ?? null })` also sets `replyLanguage` to that value.

- [ ] **Step 1: Write failing test.** `buildDispatchMetadata(null, { replyLanguage: 'en' })` contains `"reply_language":"en"`; `'fr'` and `['en']` add no key.
- [ ] **Step 2:** Run it. Expect FAIL.
- [ ] **Step 3:** Implement the plumbing and gating.
- [ ] **Step 4:** Run the test, then `pnpm exec tsc --noEmit` and `pnpm exec eslint` on the changed files. Expect PASS and clean.
- [ ] **Step 5:** Commit `feat(web): carry the chat's reply language in the session token`.

### Task 7: Picker UI, localized welcome, header label

**Files:**
- Modify:
  - `frontend/components/portal/assistant/assistant-chat.tsx` (`EmptyState`, `Composer`, `AssistantChatHeader`)
  - `frontend/components/portal/assistant/suggested-questions.tsx`
- Test: manual in the browser

**Interfaces:**
- Consumes `replyLanguage`, `chooseReplyLanguage` and `languagePending` (exposed through `useAssistant`, passed from the bubble context).
- `EmptyState` with `replyLanguage === null`:
  - It shows the title `Choose a language / ভাষা বেছে নিন` and two buttons: `English` (`lang="en"`) and `বাংলা` (`lang="bn"`).
  - Nothing else shows: no greeting, chips or "Talk instead of typing".
  - The composer input, send and mic are `disabled`, with placeholder `Choose a language first / আগে ভাষা বেছে নিন`.
  - The header's call button is hidden.
- After the pick, the greeting and chips follow the language:
  - `bn`: today's text and chips.
  - `en`, signed in: `Assalamu alaikum, {first_name}! I'm telco's assistant. I can help you check your balance and usage, find a package or recharge.` then `How can I help?`
  - `en`, guest: `Assalamu alaikum! I'm telco's assistant. I can help you find a package, check the network in your area, or answer questions about SIMs, stores and our policies. Log in to see your balance or buy a package.` then `How can I help?`
  - New `POPULAR_QUESTIONS_EN`: `What's my balance?`, `How much data do I have left?`, `Which package suits me best?`, `Why was money deducted from my balance?`, `I want to make a complaint`.
  - New `GUEST_QUESTIONS_EN`: `What monthly data packages do you have?`, `Any internet package under 300 taka?`, `How do I get a new SIM?`, `Where is the nearest care centre?`, `Is there a network problem in Dhaka?`
  - The `lang` attribute on each element follows the language.
- The header shows a small read-only label (`English` or `বাংলা`) after `· {status}` while `replyLanguage` is set.
- The assistant page's sidebar `PopularQuestionList` stays as it is. Its sends go through the same gate.

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `pnpm exec tsc --noEmit`, `pnpm exec eslint` and `pnpm exec prettier --check` on the changed files. Expect clean.
- [ ] **Step 3: Manual check** (dev server; backend and worker running).
  - The bubble opens on the picker, and the input is disabled.
  - Pick English: the English greeting and chips show.
  - Click a chip: the chat starts with `reply_language: "en"` in the token request (devtools Network).
  - End the chat and reopen: the picker shows again.
  - With no pick, a nudge click opens the picker, and the nudge starts after the pick.
  - With no pick, `/portal/assistant?q=hi` followed by send behaves the same way.
  - A resumed history chat shows no picker.
- [ ] **Step 4:** Commit `feat(web): language picker opens each new chat`.

### Task 8: Full verification

- [ ] **Step 1:** Run `cd backend && uv run pytest -q`. Expect all pass. Then re-embed the KB (full run reseeds it).
- [ ] **Step 2:** Restart the agent worker.
- [ ] **Step 3: Live test.**
  - Pick English, then type and speak Bangla for 4+ turns, including a package question and a goodbye. Expect English replies, fillers, idle check-in and goodbye.
  - Pick Bangla, then speak English the same way. Expect Bangla throughout.
  - Note any drifted turn and its run log.
- [ ] **Step 4:** Update memory: a new `telco-reply-language` memory with the contract; the filler-style and voice-modes memories link to it.
- [ ] **Step 5:** Commit the spec and plan edits if any are still uncommitted.
