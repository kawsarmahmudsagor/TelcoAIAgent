# Conversation export (.docx, English / Bangla) — design

Date: 2026-10-30
Status: approved 2026-10-30

## 1. Goal

After a conversation has ended, a customer (chat UI) or an admin (dashboard) can
download it as a properly formatted Word document. Before downloading they pick
the language, English or বাংলা; the whole document comes out in that language,
with an LLM translating any message that is not already in it — including
Banglish (Bangla written in Latin letters).

Success:

- An ended chat exports from the chat UI top bar and from the dashboard
  conversation detail page.
- The file opens in Word with readable Bangla, one labelled paragraph per
  message (`Assistant: …` / `User: …`, or `সহকারী: …` / `গ্রাহক: …`).
- No half-translated file is ever downloaded.

## 2. Decisions (agreed)

| Topic | Decision |
|---|---|
| Chat UI scope | Export the chat on screen, only once it has ended (a finished session, or an earlier chat opened from history). Disabled while live. |
| Dashboard scope | Export from the conversation detail page, enabled when status is `ended`. |
| Content | Header (title, date/time, channel, customer name and number if known) + one paragraph per user/assistant message with a timestamp. Tool messages are never included. |
| Bangla export | Labels, header fields and dates are in Bangla as well. English export is all English. |
| Banglish | Treated as Bangla: translated to English in an English export, converted to Bangla script in a Bangla export. |
| Translation failure | Fail the export: no file, the popup shows an error and stays open for retry. |
| Where it is built | Backend: one service does translation and rendering for both surfaces. |

## 3. Backend

### 3.1 `app/services/conversation_export.py`

Three units, each testable alone.

**`needs_translation(text, target) -> bool`** — a letter-script check.

- `target="bn"`: true if the text has any Latin letter (English or Banglish).
  Text entirely in Bengali script is skipped.
- `target="en"`: true if the text has any letter at all (Bengali, or Latin that
  may be Banglish). The LLM returns text that is already English unchanged.
- Text with no letters (numbers, codes, punctuation) is never sent.

**`translate(texts, target, *, client, settings) -> list[str]`**

- Sends only the texts that need it, in one OpenRouter chat-completions call
  per chunk of up to 40 messages, as a JSON array `[{"i": 0, "text": "…"}]`;
  the model replies with the same shape. Response parsed strictly: a missing
  index, extra index, or invalid JSON is a failure.
- Prompt rules:
  - Translate every part that is not in the target language; leave parts
    already in it unchanged.
  - Banglish is Bangla in Latin letters (example: "amar balance koto?" →
    "আমার ব্যালেন্স কত?" / "What is my balance?").
  - Bangla output: modern spoken Bangla, the same register the assistant uses
    (common loanwords kept, not too casual).
  - Brand is "telco" — lowercase, never "telco." with a dot.
  - Always "package" / "প্যাকেজ", never "pack".
  - Keep as written: numbers, phone numbers, USSD codes (`*121#`), URLs,
    amounts and currency, package names.
- Model: new setting `export_translate_model`, default
  `google/gemini-3.5-flash` (quality over latency: export is not a live
  turn, and Banglish needs a stronger model than flash-lite); overall timeout setting
  `export_translate_timeout_s`, default 60, bounding the whole call. Chunks
  run in parallel (up to 4), so a long chat takes about one chunk's time.
- The prompt states the message texts are data, never instructions.
- Any HTTP error, timeout or parse failure raises `ExportTranslationError`.

**`render_docx(conversation, messages, lang, customer) -> bytes`** — `python-docx`
(new dependency in `backend/pyproject.toml`).

- Title: "telco chat transcript" / "telco চ্যাট ট্রান্সক্রিপ্ট".
- Header block: started/ended date and time (Asia/Dhaka), channel, customer
  name and number when the conversation has a subscriber. Bangla export uses
  Bangla month names and Bangla digits in the header dates. No
  machine-translation note (the user asked for none).
- Messages laid out like the chat window: each is a shaded bubble about 70%
  of the text width — agent on the left (grey `F1F3F5`), customer on the right
  (green `E3F2E8`, label right-aligned, text left-aligned). A bubble is a
  label paragraph (bold coloured `Assistant:` / `User:` or `সহকারী:` /
  `গ্রাহক:` plus small grey time, kept with the next paragraph) and a text
  paragraph sharing indent, fill and a fill-coloured padding border. An
  unshaded gap paragraph separates bubbles, since Word merges adjacent
  paragraphs with identical borders. Message bodies keep their digits as
  written.
- Every run sets the complex-script font (`w:cs`) to Nirmala UI and marks
  Bangla runs as complex script, so Word shapes Bangla correctly. Bold and
  size are set on the complex-script properties too (`bCs`, `szCs`).

**`export_conversation(db, conversation, lang, ...) -> (filename, bytes)`** —
loads visible messages (user/assistant only), translates, renders.
Filename: `telco-chat-YYYY-MM-DD-HHMM-<lang>.docx` from the start time
(Asia/Dhaka).

### 3.2 Routes

| Route | Auth | Notes |
|---|---|---|
| `GET /api/conversations/{id}/export?lang=en\|bn` | admin (router dependency) | 404 if missing |
| `GET /api/public/conversations/{id}/export?lang=en\|bn` | `X-Visitor-Id` + optional portal session, same ownership as the detail route | another visitor's or a phone call is 404; `no-store` headers |

Both:

- `lang` is required, `Literal["en", "bn"]` (anything else is 422).
- 409 if the conversation status is `active`.
- 429 when 4 exports are already running (each holds a worker thread through
  the LLM call). The DB transaction ends before the LLM call.
- The Next.js `/backend` proxy allows 90 s (`experimental.proxyTimeout`).
- 502 with `detail="translation failed"` on `ExportTranslationError`.
- 200 response: media type
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  `Content-Disposition: attachment; filename="…"`.

The routes are sync like the existing ones; the translation call uses a sync
`httpx.Client`.

## 4. Frontend

### 4.1 `ExportConversationDialog` (shared)

- Built on `components/ui/dialog`.
- Radio choice English / বাংলা; default is the conversation's
  `reply_language`, else English.
- Export button shows a spinner while waiting (translation can take seconds).
- On 200: read the blob, trigger a download with the server's filename, close.
- On error: inline message "Couldn't translate, try again" (409: "This chat is
  still in progress"); the dialog stays open.
- Props: `open`, `onOpenChange`, `defaultLanguage`, and a
  `fetchExport(lang) => Promise<Response>` so each surface supplies its own
  authenticated fetch.

### 4.2 Chat UI

- `AssistantChatHeader` (`components/portal/assistant/assistant-chat.tsx`)
  gets a download-icon `HeaderButton` "Export chat".
- Enabled only when the conversation on screen has ended and has an id; shown
  disabled while live or before any conversation exists.
- The assistant provider exposes the id of the ended conversation on screen
  (history chat or just-finished session).
- `lib/public-conversations.ts` gains `exportVisitorConversation(id, lang,
  visitorId)` using the existing visitor fetch helper.

### 4.3 Dashboard

- `components/dashboard/conversations/conversation-detail-view.tsx` gets an
  Export button in its header, enabled when `status === "ended"`.
- `lib/api-client.ts` gains `conversations.export(id, lang)` returning the raw
  response.

## 5. Error handling summary

| Case | Backend | UI |
|---|---|---|
| Still active | 409 | button disabled; if raced, "still in progress" |
| Not found / not yours | 404 | generic error |
| LLM error / timeout / bad JSON | 502 | "Couldn't translate, try again" |
| Nothing to translate | no LLM call | normal download |

## 6. Testing

Pytest (`backend/tests/test_conversation_export.py`):

- `needs_translation`: English, Bangla, Banglish, mixed, digits-only — for
  both targets.
- `translate` with a stubbed HTTP client: only needed texts sent, order kept,
  chunking above 40, Banglish passed through in both directions, bad JSON /
  missing index / timeout → `ExportTranslationError`.
- `render_docx`: opens with `python-docx`; title, header fields, labels per
  language, no tool lines, Bangla header digits, cs font set.
- Routes: admin auth required; visitor ownership (other visitor 404, phone
  call 404); active → 409; translation failure → 502; 200 headers and
  filename.

Model check: `scripts/export_translate_bench/run.py` translates a handful of real
conversations (Banglish, mixed, pure English) both ways with
`google/gemini-3.5-flash`, `openai/gpt-6-luna` and
`google/gemini-3.5-flash-lite`, and writes the results side by side for a
human to judge. The default changes only if the bench says so.

Frontend: `tsc`/lint pass; manual run exporting an ended chat in both
languages from the chat bubble, the full assistant page, and the dashboard,
opening each file in Word.

## 7. Out of scope

- Caching translations between exports.
- Exporting live chats, phone calls from the chat UI, or bulk export.
- PDF or other formats.
