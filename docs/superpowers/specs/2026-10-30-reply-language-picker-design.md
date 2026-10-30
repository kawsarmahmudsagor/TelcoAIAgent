# Reply language picker — design

Date: 2026-10-30. Branch: `telco/llm-filler`.

## Goal

A browser chat opens with an English / বাংলা picker. The bot replies only in the picked
language, whatever language the customer types or speaks. The pick overrides every other
language rule: the prompt, fillers, idle check-ins, closing lines and number speech.

## Decisions (from the user)

| Topic | Decision |
|---|---|
| When the picker shows | At the start of each new chat. Reopening the bubble mid-chat does not ask again. |
| Switching mid-chat | Not allowed. The language is fixed for the chat; a new chat asks again. |
| Where | Chat bubble and the full assistant page (`/portal/assistant`). Phone calls are unchanged (auto). |
| What the bot hears | Both English and Bangla, as today. STT stays as configured (auto by default). Only replies are fixed. |
| Resuming a chat from history | Keeps that chat's language; no picker. |
| Welcome bubble and chips | Follow the pick: English text and chips for English, the current Bangla ones for Bangla. |
| Third language (e.g. Hindi) | The "could not understand" line, said in the picked language. |

## Contract

One value, `reply_language`: `"en"` or `"bn"`. When absent (phone calls, chats from before
this change), every component keeps today's per-turn behaviour.

```
picker (frontend) -> participant_attributes.reply_language -> token route (validates)
  -> dispatch metadata.reply_language -> session_context -> userdata.reply_language
  -> conversations.reply_language (stored) -> history API -> resume
```

## Frontend

- `ChatBubbleProvider` (`components/chat-bubble/chat-bubble-context.tsx`) holds
  `replyLanguage: 'en' | 'bn' | null` and `setReplyLanguage`.
  - Starts `null`. Reset to `null` when a session ends, so the next chat asks again.
  - A resumed conversation sets it from the conversation's stored language. A resumed chat
    with no stored language (from before this change) shows the picker.
  - Sent as `participant_attributes.reply_language` in the token request, like `text_start`.
- Every start path waits for a pick: typed send, mic button, "Talk instead of typing", header
  call button, nudge click, `?q=` prefill send. With no pick, the panel opens on the picker and
  the start runs right after the pick. A start never goes out with `reply_language` missing.
- `EmptyState` (`components/portal/assistant/assistant-chat.tsx`) shows the picker first: a
  short bilingual title ("Choose a language / ভাষা বেছে নিন") and two buttons, "English" and
  "বাংলা". The composer and mic stay disabled until a pick. After the pick it shows the greeting
  and chips in that language. English greeting and chip texts are added next to the Bangla ones
  in `suggested-questions.tsx`.
- The header shows the picked language as a small read-only label while a chat is open.

## Token route

`frontend/app/api/token/route.ts` passes `reply_language` into `buildDispatchMetadata` only when
it is exactly `"en"` or `"bn"`; anything else is dropped, like the other attributes.

## Backend

- `app/agent/session_context.py`: parse `reply_language` from metadata into
  `userdata.reply_language: Literal["en", "bn"] | None`.
- `Conversation.reply_language`: new nullable `String(2)` column plus an Alembic migration.
  `TranscriptRecorder` writes it when it opens the conversation.
- History API (chat history list and resume payload) returns `reply_language`.
- Resume (`transcript.py`): when resuming, the stored language wins over the metadata value,
  so a resumed chat cannot change language.
- Guest login mid-chat (`account_link`) keeps `userdata.reply_language`.

## Agent: the pick is the only language source when set

A helper `fixed_language(userdata) -> "en" | "bn" | None` is the single read point.

1. **System prompt** (`persona.build_system_prompt`): when set, append a `REPLY LANGUAGE` block
   after the editable prompt parts. It says: always reply in English (or Bangla, in Bengali
   script), whatever language the customer writes or speaks in, including their first message,
   and whatever language tools or knowledge base text use. This overrides the LANGUAGE rules
   above. The greeting uses the picked language. The block is appended, not substituted into
   the editable LANGUAGE text, because admins may edit that text. `CHANNEL_TEXT_NOTE` stays the
   last block (voice_mode's `str.replace` depends on it).
2. **Text-start and closing notes** (`persona.py`, `entrypoint.py`, `closing_offer.py`): the
   "in the language of the customer's latest message" wording becomes "in English/Bangla" when
   set.
3. **Per-turn reminder** (`closing_offer.with_reminder`, which already puts a note last in the
   main model's context because the model barely heeds earlier notes): when set, every turn's
   last note says to reply in the picked language, merged with the wrap-up/backstop reminder
   when one is due.
4. **Fillers** (`quick_reply.py`): template choice, the fast LLM filler and the care filler use
   the pick instead of the utterance's script. Echo templates already have Bangla and English
   forms of the entity; as a guard, a template line whose script differs from the pick is
   never chosen, so an English filler never carries Bangla words. `avoid()` filters by the pick.
5. **Idle check-in and goodbye** (`idle_checkin.py`): `_reply_language` returns the pick when
   set.
6. **Other-language line** (`gated_agent.py`): add a Bangla version of `OTHER_LANGUAGE_LINE`
   and say the one matching the pick (English line when unset, as today). The prompt's
   exact-line rule follows the same pick.
7. **Number speech** (`speech_numbers.py`): when set, the pick is passed in and used instead of
   guessing from the reply text.

STT, the turn gate's language checks and the dashboard STT language setting are unchanged.

## Out of scope

- Switching language mid-chat.
- Phone calls.
- A rewrite-and-retry pass for replies that drift into the wrong language. Added later only if
  test calls show drift.
- Dashboard display of a conversation's language.

## Testing

- Unit tests:
  - prompt with `en`, `bn` and `None`; the block sits before `CHANNEL_TEXT_NOTE`
  - fillers: template language, script guard, LLM filler language
  - per-turn reminder present when set, merged with wrap-up; absent when unset
  - idle check-in and goodbye lines follow the pick
  - other-language line per pick
  - number speech with a fixed language
  - `session_context` parsing; token route validation
  - conversation column written; resume keeps the stored language
- Frontend: typecheck and lint; picker gates every start path.
- Manual (needs a worker restart, see memory): pick English and speak or type Bangla, expect
  English replies and fillers. Pick Bangla and speak English, expect Bangla. Check resume,
  nudge click and the header call button.

## Risk

The main LLM may still answer in the customer's language on some turns despite the prompt.
The `REPLY LANGUAGE` block is the guard. Watch for it in the manual test.
