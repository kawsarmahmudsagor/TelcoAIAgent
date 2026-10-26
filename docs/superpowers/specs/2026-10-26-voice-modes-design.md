# Voice modes: guest text-only, dashboard "Voice responses" switch

Date: 2026-10-26 · Branch: telco/v1 · Status: approved design, awaiting spec review

## 1. Goal

Today every browser session is full voice for everyone: anyone can turn the mic on, and the
assistant always answers in voice with synced text. This change adds:

- **Guests** (not logged in) can only type, and the assistant answers in text.
- **Logged-in customers** can type or speak. Whether the assistant answers in voice or in text
  depends on a new dashboard switch, **Voice responses**.
- A guest who logs in mid-chat keeps the same conversation and gains the mic at once.

Success means:

1. A guest session never runs STT or TTS, even if the browser publishes a mic track.
2. With Voice responses ON, a logged-in session behaves exactly as it does today.
3. With Voice responses OFF, a logged-in customer's speech is transcribed and answered in text.
   No TTS runs. Filler lines ("one moment…") appear as short text messages.
4. Dashboard changes apply to sessions that start afterwards. Open sessions keep their mode.

## 2. Decisions (from brainstorming)

| Question | Decision |
|---|---|
| How many switches | One: **Voice responses**. A logged-in customer can always speak. |
| When a switch change applies | New sessions only. Config is read once at session start, as today. |
| Guest logs in mid-chat | The same session upgrades through the existing `account_link`. |
| Fillers in text mode | Shown as text (the default `session.say` behaviour with audio output off). |
| Prompt | Keep the prompt. Add one CHANNEL note when replies are text. |
| Phone path | Unchanged. Always full voice. |

## 3. Voice modes

One value per session, `VoiceMode`, decided by the agent:

| Mode | When | Audio input (STT) | Audio output (TTS) | CHANNEL note in prompt |
|---|---|---|---|---|
| `off` | guest (no `subscriber_id`) | disabled | disabled | yes |
| `text_reply` | logged in, `voice_replies_enabled = false` | enabled | disabled | yes |
| `full` | logged in, `voice_replies_enabled = true`; every phone call | enabled | enabled | no |

The **agent** enforces the mode. Hiding the mic in the browser is only UX. A guest who publishes
a track anyway gets nothing transcribed, because `session.input` audio is disabled.

livekit-agents 1.7 supports this at runtime:
- `session.input.set_audio_enabled(bool)`
- `session.output.set_audio_enabled(bool)`

When output audio is disabled, `agent_activity` passes `audio_output=None` to the generation
step. No TTS request is made, and the reply goes out on the transcription (text) output only.

## 4. Backend

### 4.1 Config field

- `AgentConfig.voice_replies_enabled: bool`, default `true`, `server_default="true"`, so
  current behaviour holds after the migration.
- One Alembic migration adds the column.
- The field follows the existing `quick_reply_enabled` path through four files:
  - `app/models/agent_config.py`
  - `ResolvedAgentConfig` in `app/services/agent_config_service.py`
  - `app/schemas/agent_config.py` (read and update schemas)
  - `app/api/routes_agent_config.py` (field list and response mapping)

### 4.2 New module `app/agent/voice_mode.py`

```python
class VoiceMode(str, Enum):
    off = "off"
    text_reply = "text_reply"
    full = "full"

VOICE_ATTRIBUTE = "voice"  # must match frontend VOICE_ATTRIBUTE

def mode_for(userdata, config) -> VoiceMode: ...          # pure: the table in §3
def channel_note(mode) -> str: ...                         # "" for full, else CHANNEL_TEXT_NOTE
async def apply(session, agent, userdata, config, room) -> VoiceMode:
    """Sets input/output audio, swaps the CHANNEL note in the agent's
    instructions if the mode changed, stores userdata.voice_mode and
    publishes the `voice` participant attribute."""
```

- `SessionUserdata` gains `voice_mode: VoiceMode | None = None`.
- `CHANNEL_TEXT_NOTE` lives in `prompt_defaults.py`:
  > CHANNEL — your replies are shown as text, not spoken. Keep the same short style. Offer to
  > show more, not to read out more.

  The note is the same in both text modes. In `text_reply`, the customer's speech reaches the
  model as ordinary user text, so the model needs nothing more.
- `build_system_prompt(userdata, config, …)` appends `channel_note(mode_for(userdata, config))`
  as its own block. It goes at the end, so `account_link`'s and `snapshot_refresh`'s in-place
  `str.replace` of the snapshot block are unaffected.
- `apply` adds or removes the note with the same `update_instructions(instructions.replace(…))`
  technique that `account_link` uses.

### 4.3 Wiring

- `entrypoint.entrypoint`: after `session.start(...)`, and before the greeting, it calls
  `await voice_mode.apply(...)`. It sits next to `account_link.publish_account`. If it fails,
  it logs the error and falls back to `off` for a guest.
- `account_link.AccountLink`: once a guest has been upgraded (the snapshot is swapped and the
  conversation linked), it calls `voice_mode.apply` with the session's start-time config. The
  mode goes from `off` to `text_reply` or `full`. The config is the one loaded at session start
  and is never re-read (decision: new sessions only). It is passed into `AccountLink` at
  construction.
- Phone path: `_build_session` has no room. Its mode is always `full`, and `apply` is not called.
- The session is still built with STT and TTS for every browser session, so an upgrade needs no
  rebuild. The cost is the ElevenLabs key lookup at start, which is unchanged from today.

### 4.4 Turn gate and fillers

- The turn gate judges voice turns only. With input audio off it gets no voice turns. Typed
  turns keep their current path (`_text_input_cb`).
- Gate fillers and the off-language line use `session.say(...)`. With output audio off, these go
  out as text. This is the chosen "fillers as text" behaviour, and no code change is needed.
- `TurnGateController` barge-in and pause logic need the agent's audio. In text modes there is
  no agent audio, so they never trigger. No change.

## 5. Frontend

### 5.1 Customer assistant

- New hook `useVoiceMode()` in `components/customer/`. It reads the agent participant's `voice`
  attribute, the same way `account-link.tsx` reads `account`. Before the agent has published it,
  the hook falls back to `useSignedIn()`: signed out gives `off`, signed in gives `full`. This
  avoids a mic flash for guests.
- `assistant-chat.tsx`: the empty-state talk button and the composer mic button render only
  when the mode is not `off`.
- `assistant-provider.tsx`: `toggleMic` does nothing when the mode is `off`, so it never starts
  a voice session for a guest. `useMicOnConnect(voiceRequested)` is also skipped when the mode
  is `off`.
- `text_reply`: the mic works as today. Agent "speaking" and audio-visualizer states are not
  shown, because the agent publishes no audio. Replies arrive as transcription text, as typed
  replies do today.

### 5.2 Dashboard

- `/dashboard/chatbot` gets a **Voice responses** row, built from `switch-row.tsx` and the
  `config-draft.ts` pattern used by `quick_reply_enabled`.
  - Hint text: "Off: logged-in customers can still speak; the assistant replies in text.
    Guests always chat in text. Applies to new chats."
- `lib/types/agent-config.ts` gets the new field in both the read and the update types.

## 6. Error handling

- If `voice_mode.apply` fails at start, the agent logs the error and disables both audio
  directions. A failure can never give a guest voice.
- If `apply` fails on upgrade, the agent logs it and the session stays `off`. The customer can
  still type, and a fresh session (reload) gets the right mode.
- A missing or unknown `voice` attribute in the browser falls back to `useSignedIn()`.

## 7. Testing

pytest (`backend/tests/test_voice_mode.py`):
- `mode_for`: guest gives `off` for either config value. Logged in gives `text_reply` or `full`
  by config. A phone call gives `full`.
- `apply` on a fake session/agent/room:
  - it sets the input and output flags;
  - it publishes the `voice` attribute;
  - it adds the CHANNEL note when the mode goes `full` to text and removes it going text to
    `full`;
  - it leaves the instructions unchanged when the mode is unchanged.
- `build_system_prompt` contains `CHANNEL_TEXT_NOTE` for `off` and `text_reply`, and not for
  `full`. The snapshot block is still replaceable.
- `account_link` upgrade calls `apply`, and the mode becomes `text_reply` or `full`.
- Agent config API round-trips `voice_replies_enabled`. The default is `true`.
- `alembic check` is clean.

Frontend: `pnpm typecheck`, `pnpm lint`.

Manual (needs a live LiveKit):
1. Guest: no mic button. A typed question gets a text reply, and the agent publishes no audio
   track.
2. Log in mid-chat: the mic appears, and the conversation carries on.
3. Voice responses ON: speak, and the reply is voice.
4. Turn it OFF in the dashboard and start a new chat: speak, and the reply and any filler are
   text only.

## 8. Out of scope

- Live switching of open sessions when the dashboard changes.
- Admin `/dashboard/listen` page.
- Per-customer voice preference.
- Rewording the STYLE block. The CHANNEL note covers text mode.
