# RealEstateAgent `latency-improvement` branch: what changed and what to port

Source: `C:\Users\BS23-DESKTOP-00038\Projects\RealEstateAgent`, branch `latency-improvement`.
Status: ported to TelcoAIAgent on 2026-10-26 (uncommitted at the time of writing), with
telco wording and the fixes listed under each item, including the per-agent STT model and
language dashboard fields (migration `c8f2a6d4e9b1`; language defaults to auto-detect, not
Bangla). Not ported: the branch's 20 s / 10 s idle timings.

## 1. Scope of the branch

Against `master` the branch looks huge (56 commits, 236 files), but it was cut from
`fix/finalFeedback`. The latency work is only the last two commits:

| Commit | Date | Message |
|---|---|---|
| `3e50323` | 2026-10-22 | latency reduced enough |
| `82c8e8b` | 2026-10-23 | latency improved, average time under 3s |

Diff: `git diff fix/finalFeedback latency-improvement` — 46 files, +4179 / −221.
Of that, ~1,400 lines are tests and ~1,200 are Bangla/real-estate regex tables.

The TelcoAIAgent agent is a fork of the same skeleton (`gated_agent`, `turn_gate`,
`turn_judge`, `turn_router`, `prefetch`, `quick_reply`, `idle_checkin`, `run_log`,
`voice_level`, `elevenlabs_keys`). None of the branch's new symbols exist in Telco yet,
so every item below is a candidate.

## 2. Where the latency came from

A gated voice turn goes: caller stops → STT final → Jev judge (+ router/extractor) →
quick reply filler or main LLM → TTS → first audio. The branch shortens the time to
**first audio** in five ways, and makes the timeline measurable.

### 2.1 Jev warm-up while the greeting plays

- `gated_agent.jev_warm_up(...)` builds one throwaway judge request shaped like a real
  first turn (`"hello"`, same `lookup` / `knowledge_base` flags) with a 10 s timeout.
- `TurnGateController.warm()` fires it once, fire-and-forget. `entrypoint` calls
  `agent.gate.warm()` right after `session.start()`, beside `prefetcher.warm()`.
- Why: the first real Jev call paid the provider cold start and timed out at 1.5 s, so
  turn 1 went through unjudged (bystanders included).
- Cost: one tiny OpenRouter call per session.
- **Port: yes.** Small, self-contained, no domain content. Highest value per line.

### 2.2 Rule-based fast extract (skip the router LLM)

- `turn_router.fast_extract(text, history, last_search, shown_count, allow_refine=True)`:
  a lexicon tokenizer (areas, property types, rent/buy, bedrooms, lakh/crore units,
  budgets, amenities, Bangla number words, Bangla case suffixes, NFC normalisation).
- It answers only when it understands every word and nothing earlier in the call could
  change the arguments. Anything else returns `None`.
- `Prefetcher.start()` stores the result in `_fast[key]`. In the accepted-turn path,
  when `judgement.lookup == "listings"` and a fast result exists, the prefetch uses it
  and skips awaiting the extractor LLM.
- Saves one LLM round trip (~0.5–1.5 s) on plain first requests.
- **Port: the pattern, not the code.** The lexicon is real-estate. Telco equivalent: a
  `fast_extract` for package search ("১০ জিবি ৩০ দিনের প্যাক", "500 মিনিট", price caps,
  validity). Our `turn_router._SYSTEM` already lists the fields to cover. Keep the
  same rule: return `None` on any unknown word, negation, or prior search to refine.

### 2.3 Instant template fillers (skip the filler LLM)

- `quick_reply.fast_filler(utterance, lookup, history, avoid, cache)` picks a filler line
  in <1 ms from fixed Bangla/English lists instead of asking the small model:
  - `CATEGORY_1_CHECKING`, `CATEGORY_2_UNDERSTANDING`, `CATEGORY_4_AFFIRMATIONS`.
  - `CATEGORY_3_TEMPLATES` echo the caller's query tail, e.g. "জি, {x}-এর বিস্তারিত দেখছি।"
    where `{x}` comes from `extract_bn_tail_x` (area + bedrooms + size, budget, visit…).
  - Scoring: +200 tailored to the query, +100 fresh opener (no "জি," twice in a row),
    +80..100 if the line is already in the audio cache.
  - Every line still passes `safe_filler` (no numbers/money/contacts the caller didn't say).
- `QuickReplyRuntime.compose()` tries `fast_filler` first and falls back to the model.
- `route()` now takes `text=` and sends **any** turn matching `_SUBSTANTIVE_QUESTION_RE`
  to `"filler"`, and any `listings/offers/knowledge_base` lookup to `"filler"` regardless
  of `lookup_p`. Before, a weak lookup guess got no filler.
- **Port: yes, with Telco content.** Generic categories 1/2/4 port almost as-is. The
  `{x}` echo needs telco slots (pack size, validity, balance, recharge, complaint).
  Keep our existing guard: `pending_action` / `pending_case` still route to the main
  model (OTP and confirmations must never get a filler).

### 2.4 TTS audio cache

- New `audio_cache.py`: `AudioCachingTTS` wraps the raw TTS **inside** the sentence
  `StreamAdapter`, for both ElevenLabs and OpenRouter voices.
- Any sentence of ≤14 words is looked up: exact normalised match, else fuzzy match
  (`difflib` ratio ≥ 0.82) with identical "entities" (area, bedrooms, size). A hit
  replays stored PCM (~0 ms TTFB, no TTS credits). A miss proxies upstream and saves
  the PCM as WAV in `backend/storage/audio_cache/quick_responses/` + `index.json`.
- Combined with 2.3, repeated filler lines become instant after the first call.
- **Port: yes, but fix these first** (they matter more for telco than real estate):
  1. **Wrong-number risk.** The cache wraps *every* sentence, not only fillers, and
     entities do not include numbers. "আপনার ব্যালেন্স ৫০ টাকা" and "...৬০ টাকা" are
     ~95 % similar, so the second would replay the first's audio. For balances, data
     left and prices this is a correctness bug. Restrict caching to filler lines (cache
     at the filler call site, or tag them), or require exact match whenever the text
     contains a digit.
  2. Cache key ignores the TTS model (`eleven_v4_turbo` vs `eleven_v3`) and sample rate.
  3. `record_hit` rewrites `index.json` on every hit, synchronously, on the event loop.
  4. No size cap or eviction; all WAVs are preloaded into memory at startup.
  5. Fuzzy match is O(n) `SequenceMatcher` per sentence; fine for hundreds of lines, not
     thousands.

### 2.5 STT, VAD and provider tweaks

- **ElevenLabs batch STT.** New `elevenlabs_keys.BatchElevenLabsSTT` (Scribe `scribe_v2`
  per turn, 8 s per-attempt timeout, max 1 retry) wrapped in `stt.StreamAdapter` with
  the VAD. Default `ELEVENLABS_STT_MODEL` changed `scribe_v2_realtime` → `scribe_v2`.
  `_batch_stt()` now treats this like OpenRouter STT, so `BATCH_STT_ENDPOINT_MIN_DELAY_S`
  (2.0 s) applies. Realtime mode gained `language_code` and `tag_audio_events=False`.
  - Reason: realtime Scribe guessed the language from the first syllables and wrote
    Bangla as Turkish. Batch hears the whole turn.
  - Note: this is an **accuracy** fix that adds latency (whole-turn upload + 2 s
    endpoint delay). It is not where the speed came from.
  - New per-agent DB fields `elevenlabs_stt_model`, `elevenlabs_stt_language` (two
    migrations, schema, service, dashboard voice section).
  - **Port: optional.** Only if Telco sees the same language misdetection.
- **Silero VAD tuned.** `VAD_ACTIVATION_THRESHOLD` (default 0.76), `VAD_MIN_SPEECH_DURATION`
  (0.25 s) passed to `silero.VAD.load()`. Fewer false turns from coughs and room noise.
  **Port: yes**, cheap. Mind the mismatch below.
- **Reasoning effort.** `"none"` is sent as `"minimal"` to OpenRouter, because some
  endpoints (Gemini 3.5 Flash Lite) reject `"none"` with a 400. `quick_models` adds
  `grok-4.7`, `gpt-oss-120b`, `claude-haiku-4.5`, `gemini-3.5-flash` with per-model effort.
  **Port: yes** for the none→minimal guard.
- **Shared HTTP client.** The per-call keep-alive `httpx.AsyncClient` is stored on the
  session and reused by the idle check-in LLM. Telco already has the keep-alive client.

## 3. Turn-gate changes (quality, not speed)

These ride along in the same commits. Most are tied to noisy-room Bangla calls.

| Change | Where | Port? |
|---|---|---|
| Voice isolation: drop a turn whose 75th-pct level is below `TURN_SPEECH_FLOOR_DBFS` or `ref − TURN_SPEECH_MARGIN_DB`, unless the bot just asked / caller confirmed and Jev still scores it addressed | `gated_agent.on_user_turn_completed`, `voice_level.current_turn_level` | Maybe; tune on telco calls |
| `_metered` replaces frames below the cutoff with silence (350 ms hangover) before STT | `GatedAgent._metered` | Careful: can clip quiet callers |
| Drop transcripts whose STT language is not bn/en | `on_user_input_transcribed` | Yes |
| Phone numbers / emails never count as filler or "no script" | `turn_gate._PHONE_OR_CONTACT_RE` | Yes (MSISDN, OTP) |
| Bengali letters present ⇒ script is `bn` (code-mixed "booking টি confirm করুন") | `turn_gate.classify_script` | Yes |
| Presence checks ("শুনতে পাচ্ছেন", "hello?", "can you hear me") always accepted; judge prompt updated | `turn_gate.is_presence_check`, `turn_judge._INSTRUCTIONS` | Yes |
| A final sentence that only *starts* with a stop phrase is judged, not auto-interrupt | `turn_gate.is_bare_stop_phrase` | Yes |
| `_bot_just_asked` also matches polite Bangla prompt endings (বলবেন, করবেন, চান…) | `gated_agent` | Yes |
| Dropped turn that looks like a question ⇒ says a Bangla "please repeat" line | `gated_agent` | Maybe |
| try/except around accepted-turn processing and the LLM stream, with spoken fallback | `gated_agent` | Yes (robustness) |
| Customer name sync from any accepted turn into booking state | `_sync_customer_name` | Domain; skip |

## 4. Idle check-in rewrite

- Defaults changed: `IDLE_CHECKIN_S` 300 → **20**, `IDLE_END_S` 30 → **10**. Real estate
  wanted an aggressive "sales trail". For a telco support line this is too pushy; keep
  ours unless product says otherwise.
- `compose_check_in()` asks the quick-reply model (2.5 s timeout, JSON `{"text": ...}`)
  for a context-aware line. Fallback `_pick_check_in_line()` uses booking state and
  shown listings.
- Does not interrupt while `user_state == "speaking"`; re-checks after the LLM returns.
- **Port: the mechanism** (LLM line + speaking guard). Rewrite the prompt for telco
  (pending recharge, pending complaint, last package shown).

## 5. Run-log timeline (how "under 3 s" was measured)

- `run_log.log_config(stt=, tts=, llm=)` prints the active pipeline at session start.
- Per turn, new timestamps: `user_started_at`, `stt_heard_after` (caller stop → first
  final, measured even for turns the library metrics skip), each Jev call, router,
  tools, filler queued, `quick_speaking_at`, `detail_speaking_at`, `turn_finished_at`.
- `_build_timeline()` prints a sorted table per turn: start time, offset from "caller
  stopped", duration, phase, details. "Agent started speaking quick response (X s after
  caller stopped)" is the headline number.
- **Port: yes, first.** Without it we cannot prove any of the other changes help.

## 6. Other bits in the diff

- `worker.py` / `entrypoint.py`: on Windows, reconfigure stdout/stderr to UTF-8 so Bangla
  log lines don't crash the worker. **Port: yes**, trivial.
- `persona.py` / `prompt_defaults.py`: viewing-booking prompt rules (real estate only).
- `booking.py`, `tools/booking_form.py`, `tools/reschedule_viewing.py`, `routes_bookings.py`:
  booking/name handling. Domain; skip.
- Frontend: `voice-section.tsx` STT model/language pickers; `useMicOnConnect.ts` small fix.
- Env example and config defaults disagree: VAD threshold 0.68 vs 0.76, speech margin
  14 vs 18 dB, floor −50 vs −48 (and `GateConfig` default −42). Pick one set when porting.

## 7. Suggested port order for TelcoAIAgent

1. Run-log timeline (§5) + UTF-8 stdout fix. Measure a baseline on current Telco.
2. Jev warm-up (§2.1). Reasoning none→minimal guard (§2.5).
3. Template fillers with telco lines (§2.3), keeping the `pending_action/pending_case` guard.
4. Audio cache **restricted to filler lines** (§2.4 fixes 1–4).
5. Telco `fast_extract` for package search (§2.2), with a bench in `scripts/router_bench`.
6. Turn-gate fixes from §3 marked "Yes". VAD tuning.
7. Re-measure. Only then consider voice isolation, batch Scribe, and idle check-in changes.

Each step is independent and can ship behind the existing settings flags.
