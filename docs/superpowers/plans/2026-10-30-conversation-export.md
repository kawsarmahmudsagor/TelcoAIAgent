# Conversation Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export an ended conversation as a formatted .docx in English or Bangla (LLM-translated, Banglish included) from the chat UI top bar and the dashboard detail page.

**Architecture:** One backend service (`app/services/conversation_export.py`) detects which messages need translation, translates them in batched OpenRouter calls, and renders the .docx with python-docx. Two thin routes (admin, visitor) call it. The frontend has one shared dialog that takes a surface-specific fetch function.

**Tech Stack:** FastAPI (sync routes), SQLAlchemy, httpx (sync client), python-docx, pytest; Next.js + React + shadcn `ui/dialog`.

**Spec:** `docs/superpowers/specs/2026-10-30-conversation-export-design.md`

## Global Constraints

- Export only conversations with `status == "ended"`; active is 409.
- `lang` is `Literal["en", "bn"]`, required.
- Tool messages never appear in an export.
- Translation failure of any kind is 502 `detail="translation failed"`; never a partial file.
- Brand in all copy and prompts: `telco`, lowercase, never `telco.`.
- Always "package" / "প্যাকেজ", never "pack".
- Labels: en `Assistant:` / `User:`; bn `সহকারী:` / `গ্রাহক:`.
- Title: en `telco chat transcript`; bn `telco চ্যাট ট্রান্সক্রিপ্ট`.
- Times in Asia/Dhaka. Bangla header dates use Bangla digits and month names; message bodies keep digits as written.
- Filename: `telco-chat-YYYY-MM-DD-HHMM-<lang>.docx` from `started_at` in Asia/Dhaka.
- Media type: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
- Settings: `export_translate_model = "google/gemini-3.5-flash"`, `export_translate_timeout_s = 60`.
- Chunk size: 40 messages per LLM call.
- Complex-script font: `Nirmala UI` (`w:cs`).

## Review Focus

1. A chat that just disconnected may still be `active` in the DB for a moment (recorder closes it async): the UI shows "This chat is still in progress" on 409 instead of a generic error. Pinned in Task 5 dialog error mapping.
2. The LLM returns the translations in a different order or drops one: must fail, never mis-assign a line to the wrong message. Pinned in Task 1 `test_translate_missing_index_fails`.
3. A message with an empty or `None` text: skipped in the document, never sent to the LLM. Pinned in Task 3 `test_export_skips_empty_messages`.
4. A guest whose screen holds several ended sessions: export covers only the last ended conversation (the one with an id). Documented in Task 6 context comment.
5. The model wraps its JSON in a ```json fence: parse the fenced body rather than fail. Pinned in Task 1 `test_translate_accepts_fenced_json`.

---

### Task 1: Translation (detection + batched LLM calls)

**Files:**
- Create: `backend/app/services/conversation_export.py`
- Modify: `backend/app/config.py` (add the two settings next to `quick_reply_model`)
- Test: `backend/tests/test_conversation_export.py`

**Interfaces:**
- Produces:
  - `ExportLang = Literal["en", "bn"]`
  - `class ExportTranslationError(Exception)`
  - `needs_translation(text: str, target: ExportLang) -> bool`
  - `translate(texts: list[str], target: ExportLang, *, client: httpx.Client, settings: Settings) -> list[str]` — same length and order as `texts`; untouched texts returned as-is.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("text,target,expected", [
    ("What is my balance?", "bn", True),
    ("amar balance koto", "bn", True),
    ("আমার ব্যালেন্স কত?", "bn", False),
    ("আমার balance কত?", "bn", True),
    ("*121# 500", "bn", False),
    ("What is my balance?", "en", True),
    ("amar balance koto", "en", True),
    ("আমার ব্যালেন্স কত?", "en", True),
    ("*121# 500", "en", False),
])
def test_needs_translation(text, target, expected): ...

def test_translate_sends_only_needed_texts()      # httpx.MockTransport captures body; "আমার ব্যালেন্স কত?" absent from the request for target bn; output order kept
def test_translate_banglish_both_ways()           # "amar net slow keno" is sent for bn and for en
def test_translate_chunks_above_40()              # 41 needed texts -> 2 requests
def test_translate_accepts_fenced_json()          # reply content wrapped in ```json ... ``` parses
def test_translate_missing_index_fails()          # reply lacks one index -> ExportTranslationError
def test_translate_bad_json_fails()               # -> ExportTranslationError
def test_translate_http_error_fails()             # 500 and httpx.TimeoutException -> ExportTranslationError
def test_translate_prompt_rules()                 # system prompt contains "Banglish", "telco", "প্যাকেজ", "*121#"
```

- [ ] **Step 2: Run** `cd backend; uv run pytest tests/test_conversation_export.py -v` — expect import errors.

- [ ] **Step 3: Implement.** Bengali letters: `[ঀ-৿]`; Latin letters: `[A-Za-z]`. Request: `POST {settings.openrouter_base_url}/chat/completions`, bearer `settings.openrouter_api_key`, `model=settings.export_translate_model`, `reasoning={"effort": "none"}`, `temperature=0`, user content `json.dumps([{"i": n, "text": t}, ...], ensure_ascii=False)`; reply must be a JSON array of `{"i", "text"}` covering exactly the sent indices. System prompt states the spec §3.1 rules with the Banglish example `"amar balance koto?"` → `"আমার ব্যালেন্স কত?"` / `"What is my balance?"`.

- [ ] **Step 4: Run tests** — expect PASS.

- [ ] **Step 5: Commit** `feat(export): translate conversation messages for export`

### Task 2: .docx rendering

**Files:**
- Modify: `backend/pyproject.toml` (add `python-docx>=1.1`; run `uv add python-docx`)
- Modify: `backend/app/services/conversation_export.py`
- Test: `backend/tests/test_conversation_export.py`

**Interfaces:**
- Produces:
  - `@dataclass ExportLine: role: Literal["user", "assistant"]; text: str; at: datetime`
  - `@dataclass ExportHeader: started_at: datetime; ended_at: datetime | None; channel: str; customer_name: str | None; customer_msisdn: str | None`
  - `render_docx(header: ExportHeader, lines: list[ExportLine], lang: ExportLang) -> bytes`
  - `bangla_digits(s: str) -> str`

- [ ] **Step 1: Write failing tests** (open bytes with `docx.Document(io.BytesIO(...))`):

```python
def test_render_en_labels_and_title()     # paragraphs contain "telco chat transcript", "Assistant:", "User:"; no "telco."
def test_render_bn_labels_and_digits()    # "telco চ্যাট ট্রান্সক্রিপ্ট", "সহকারী:", "গ্রাহক:"; header date has Bangla digits (e.g. "৩০"); body "01712345678" kept as written
def test_render_header_customer()         # name + msisdn present when given; absent lines when None
def test_render_sets_cs_font()            # every run's rPr rFonts w:cs == "Nirmala UI"
```

- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement.** Label run bold, colour assistant `1F6FEB` / user `2E7D32`; time run 9 pt grey `6B7280`; channel shown as "Web chat"/"ওয়েব চ্যাট" for `inbound_chat`, "Phone call"/"ফোন কল" when phone, else raw value. Bangla months: জানুয়ারি…ডিসেম্বর.
- [ ] **Step 4: Run tests** — PASS.
- [ ] **Step 5: Commit** `feat(export): render conversation transcript as docx`

### Task 3: Export orchestration + routes

**Files:**
- Modify: `backend/app/services/conversation_export.py`
- Modify: `backend/app/api/routes_conversations.py` (new route after `get_conversation`)
- Modify: `backend/app/api/routes_public_conversations.py` (new route after `get_visitor_conversation`)
- Test: `backend/tests/test_conversation_export.py` (route tests reuse the room-prefix cleanup pattern from `test_public_conversations.py`)

**Interfaces:**
- Consumes: `translate`, `render_docx`, `ExportLine`, `ExportHeader` (Tasks 1–2); `conversation_repo.list_visible_messages`, `conversation_repo.get_for_visitor`.
- Produces:
  - `export_conversation(db: Session, conversation: Conversation, lang: ExportLang, *, client: httpx.Client | None = None, settings: Settings | None = None) -> tuple[str, bytes]` — raises `ConversationStillActive` (new exception) or `ExportTranslationError`.
  - `GET /api/conversations/{id}/export?lang=` and `GET /api/public/conversations/{id}/export?lang=`.

- [ ] **Step 1: Write failing tests** (monkeypatch `conversation_export.translate` for route tests):

```python
def test_export_skips_empty_messages()          # None/"  " text rows absent from the doc and from translate()'s input
def test_admin_export_ok()                       # 200, media type, Content-Disposition filename matches r"telco-chat-\d{4}-\d{2}-\d{2}-\d{4}-bn\.docx"
def test_admin_export_requires_admin(anon_api)   # 401
def test_admin_export_active_409()
def test_admin_export_translation_502()          # translate raises -> 502 {"detail": "translation failed"}
def test_admin_export_bad_lang_422()             # lang=fr
def test_visitor_export_ok()                     # own conversation, Cache-Control no-store
def test_visitor_export_other_visitor_404()
def test_visitor_export_phone_call_404()
def test_visitor_export_active_409()
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Service owns an `httpx.Client(timeout=settings.export_translate_timeout_s)` when none passed. Customer name/msisdn from `Subscriber` when `subscriber_id` set. Routes map exceptions to 409/502 and return `Response(content, media_type=..., headers={"Content-Disposition": f'attachment; filename="{name}"'})`; the public one adds `_NO_STORE`.
- [ ] **Step 4: Run** `uv run pytest tests/test_conversation_export.py tests/test_conversations_api.py tests/test_public_conversations.py -v` — PASS.
- [ ] **Step 5: Commit** `feat(export): admin and visitor conversation export routes`

### Task 4: Translation model bench

**Files:**
- Create: `scripts/export_translate_bench.py`

- [ ] **Step 1: Implement** `main()`: takes `--conversations N` (default 6) and `--out PATH` (default scratch `export_bench.md`). Picks the N most recent ended conversations whose messages include Banglish, mixed and English (falls back to a built-in sample list when the DB has fewer). For each of `google/gemini-3.5-flash`, `openai/gpt-6-luna`, `google/gemini-3.5-flash-lite` and each target, call `translate` with `settings.model_copy(update={"export_translate_model": m})`; write a Markdown table original | model A | B | C plus wall time per model.
- [ ] **Step 2: Run** `cd backend; uv run python ../scripts/export_translate_bench.py` — the file is written with 3 model columns and no exceptions.
- [ ] **Step 3: Commit** `chore(export): translation model bench`

### Task 5: Shared export dialog + fetch helpers

**Files:**
- Create: `frontend/components/customer/export-conversation-dialog.tsx` (used by portal and dashboard; sits beside other shared customer UI)
- Modify: `frontend/lib/public-conversations.ts`
- Modify: `frontend/lib/api-client.ts`

**Interfaces:**
- Produces:
  - `exportVisitorConversation(visitorId: string, conversationId: string, lang: 'en' | 'bn'): Promise<Response>` (raw, not `res.ok`-checked)
  - `api.conversations.export(id: UUID, lang: 'en' | 'bn'): Promise<Response>` (raw, `credentials: 'include'`)
  - `ExportConversationDialog({ open, onOpenChange, defaultLanguage, fetchExport }: { open: boolean; onOpenChange(open: boolean): void; defaultLanguage: 'en' | 'bn' | null; fetchExport(lang: 'en' | 'bn'): Promise<Response> })`
  - `downloadResponse(res: Response): Promise<void>` — filename from `Content-Disposition`, fallback `telco-chat.docx`.

- [ ] **Step 1: Implement.** Two radio options "English" and "বাংলা" (`lang="bn"`), default `defaultLanguage ?? 'en'`. Export button disabled + spinner while pending. Error text: 409 → "This chat is still in progress"; any other failure → "Couldn't translate, try again". Dialog stays open on error, closes on success.
- [ ] **Step 2: Verify** `cd frontend; npx tsc --noEmit; npm run lint` — no errors.
- [ ] **Step 3: Commit** `feat(web): conversation export dialog`

### Task 6: Chat UI export button

**Files:**
- Modify: `frontend/components/portal/assistant/assistant-provider.tsx`
- Modify: `frontend/components/portal/assistant/assistant-chat.tsx`

**Interfaces:**
- Consumes: Task 5 `ExportConversationDialog`, `exportVisitorConversation`.
- Produces: `AssistantContextValue.exportableId: string | null` — the ended conversation on screen: `resumedId`, else the id of the last guest session that ended (set in the existing `Disconnected` handler from `conversationIdRef`, cleared by `newChat`, `startOverForLogin` and the account-change effect); always `null` while `isConnected || connecting`. A guest with several ended sessions on screen exports only the last one.

- [ ] **Step 1: Implement** `exportableId` in the provider and add it to the context value.
- [ ] **Step 2: Implement** in `AssistantChatHeader` a `HeaderButton` labelled "Export chat" with lucide `DownloadIcon`, placed before the history button, disabled when `exportableId` is null (extend `HeaderButton` with a `disabled` prop if it lacks one), opening `ExportConversationDialog` with `defaultLanguage={replyLanguage}`.
- [ ] **Step 3: Verify** `npx tsc --noEmit; npm run lint` — no errors. Manual: end a chat in the bubble and on `/portal/assistant`, export en and bn, open both in Word; button disabled during a live chat; history chat exports.
- [ ] **Step 4: Commit** `feat(web): export the ended chat from the assistant header`

### Task 7: Dashboard export button

**Files:**
- Modify: `frontend/components/dashboard/conversations/conversation-detail-view.tsx`
- Modify: `backend/app/schemas/conversation.py` (`ConversationOut` gains `reply_language: str | None = None`)
- Modify: `frontend/lib/types` conversation types (`reply_language: 'en' | 'bn' | null`)

**Interfaces:**
- Consumes: Task 5 `ExportConversationDialog`, `api.conversations.export`.

- [ ] **Step 1: Implement** an outline "Export" button (lucide `DownloadIcon`) before Delete in `PageHeader` actions, disabled when `c.status !== 'ended'`, opening the dialog with `defaultLanguage={c.reply_language}`.
- [ ] **Step 2: Verify** `npx tsc --noEmit; npm run lint`. Manual: export an ended chat from `/dashboard/conversations/<id>` in both languages; live conversation shows the button disabled.
- [ ] **Step 3: Commit** `feat(dashboard): export a conversation from its detail page`
