# Prompt Caching and Compact Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the main model's prompt cacheable and about 40% shorter, with the agent saying the same things.

**Architecture:** Part 1 adds cached-token counts to the run log, then applies cache fixes only if a live call shows a low hit rate. Part 2 moves the rules shared across prompts into one module, rewrites `DEFAULT_IDENTITY_AND_RULES` in fewer words, locks every must-hold rule with a checklist test, and proves the replies match with a before/after `reply_bench` comparison.

**Tech Stack:** Python 3.11, livekit-agents (`LLMMetrics`), OpenRouter via `livekit.plugins.openai`, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-06-prompt-caching-compact-design.md`

## Global Constraints

- Branch: `fix/promptCachingCompact`. Commit after each task; push only when the user asks.
- Never run the full pytest suite: it wipes and reseeds the dev KB. Run the named files only.
- The Telco Postgres (`localhost:5435`) must be up for `reply_bench` and for any live call: `docker compose up -d` in the repo root.
- Restart the agent worker after code changes before a live call; `start` mode doesn't reload.
- Bot wording rules stay: "package"/"প্যাকেজ", never "pack"/"প্যাক", in every form; the brand is "telco", never "telco."; modern spoken Bangla.
- Kept word for word: both HARD RULE paragraphs and the "Both hard rules override…" line, the SECURITY paragraph, "I could not understand that. Could you kindly repeat that?", and the placeholders `{agent_name}`, `{operator_name}`, `{knowledge_scope}`, `{current_date}`.
- Target size: `DEFAULT_IDENTITY_AND_RULES` at most 9,500 characters (about 15,086 today).
- New modules take no livekit or DB imports, like `prompt_defaults`.

## Review Focus

1. **A dashboard-customised prompt in the DB:** the new default never reaches the agent. Expect `reply_bench` to print its NOTE line, and the user to be asked before any comparison is trusted. Covered in Task 5, Step 1.
2. **LLM metrics without `prompt_cached_tokens`** (another provider, or an old plugin): the run log must print `0 cached`, not crash. Covered by a test in Task 1.
3. **A shared-rule constant edited later with literal `{` or `}`:** `render_template` would break the main prompt. The shared constants must hold no braces. Covered by a test in Task 4.
4. **A Bangla-pick or English-pick chat:** the compacted LANGUAGE section must not fight the `REPLY LANGUAGE` block. The existing `test_prompt_fixed_*` tests must pass unchanged. Covered in Task 6, Step 4.
5. **A guest:** the compacted rules for guests must still hold: no package activation offer, how points are earned, care centres via the tool. The checklist in Task 6 renders the guest prompt too.

---

### Task 1: Cached tokens in the run log

**Files:**
- Modify: `backend/app/agent/run_log.py` (LLMMetrics branch near line 378; `_on_close` near line 443)
- Test: `backend/tests/test_run_log.py`

**Interfaces:**
- Produces: the run-log "AI model" line ends `(<in> tokens in, <cached> cached, <out> out)`. The call summary gains a row `Prompt cache` with the value `<pct>% of input tokens cached`, or `no AI model calls` when there were none.

- [ ] **Step 1: Write the failing tests** in `tests/test_run_log.py`, following the existing `test_a_turn_logs_every_part_and_a_summary` setup:
  - `test_ai_model_line_shows_cached_tokens`: an `LLMMetrics` with `prompt_tokens=7262, prompt_cached_tokens=6100, completion_tokens=85` → the log contains `(7262 tokens in, 6100 cached, 85 out)`.
  - `test_ai_model_line_without_cache_says_zero`: the metrics object has no `prompt_cached_tokens` attribute (use a `SimpleNamespace` or a subclass that deletes it) → the log contains `0 cached`.
  - `test_call_summary_shows_cache_share`: two LLM calls of (1000 in, 0 cached) and (1000 in, 800 cached), then close → the summary contains `Prompt cache` and `40% of input tokens cached`.
- [ ] **Step 2: Run them and confirm they fail**
  Run: `cd backend && uv run pytest tests/test_run_log.py -q`
  Expected: the 3 new tests FAIL; the rest pass.
- [ ] **Step 3: Implement.** Read the cached count with `getattr(m, "prompt_cached_tokens", 0) or 0`. Keep running totals `self._prompt_tokens` and `self._cached_tokens` on the logger. Write the summary row after "Fastest / slowest", rounding the percentage to a whole number.
- [ ] **Step 4: Run the tests and confirm they pass** (same command; all pass).
- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/agent/run_log.py backend/tests/test_run_log.py
  git commit -m "feat(run-log): show cached input tokens per call and per call summary"
  ```

### Task 2: Measure the cache hit rate (checkpoint, no code)

- [ ] **Step 1:** Ask the user to start the Telco stack, restart the agent worker, and make one voice call of at least 6 turns as a logged-in customer.
- [ ] **Step 2:** Read the newest `logs/run_*.log`. Record each "AI model" line's in/cached numbers and the `Prompt cache` summary row.
- [ ] **Step 3: Decide.** If the main-model calls after the first are mostly above 50% cached, skip Task 3 and go to Task 4. Otherwise do Task 3, re-measuring with Steps 1–2 after each of its parts and stopping once the rate is high.

### Task 3: Cache fixes (only if Task 2 shows a low rate)

**Files:**
- Modify: `backend/app/config.py` (next to `openrouter_model`, line 88), `backend/app/agent/entrypoint.py` (`_build_llm`, line 410), `backend/app/agent/prompt_defaults.py`, `backend/app/agent/persona.py` (`build_system_prompt`)
- Test: `backend/tests/test_prompts.py`, plus a `_build_llm` test next to the existing entrypoint tests (`tests/test_gated_session.py` imports `entrypoint`)

**Interfaces:**
- Produces: `Settings.openrouter_provider_order: list[str] = []`. When it's not empty, `_build_llm` sends `extra_body["provider"] = {"order": [...], "allow_fallbacks": True}` alongside the existing `reasoning` key.

Do the parts in order; stop when Task 2's re-measure is high.

- [ ] **Part A, provider pin.**
  - Test `test_openrouter_provider_order_reaches_the_request`: the setting `["openai"]` puts `{"order": ["openai"], "allow_fallbacks": True}` in the built LLM's `extra_body`; an empty list adds no `provider` key.
  - Implement, run `uv run pytest tests/test_gated_session.py -q`, then commit `feat(agent): optional OpenRouter provider pin for prompt caching`.
  - The user sets `OPENROUTER_PROVIDER_ORDER` in the root `.env`, then re-measure.
- [ ] **Part B, date after the snapshot.**
  - Test `test_current_date_follows_the_snapshot`: in `build_system_prompt` output, `CURRENT DATE:` comes after `ACCOUNT SNAPSHOT` and the identity block holds no time of day.
  - Implement: remove the `CURRENT DATE` paragraph from `DEFAULT_IDENTITY_AND_RULES` and append the same sentence after the snapshot in `build_system_prompt`. Keep `current_date` in the template values, so a custom prompt that uses `{current_date}` still renders.
  - Run `uv run pytest tests/test_prompts.py tests/test_snapshot_refresh.py -q`, then commit `fix(agent): current date after the snapshot so the rules prefix caches`.
- [ ] **Part C, tool order.**
  - Log the tool names in the order sent across two calls of the Task 2 session. If they differ, sort the tool list once at agent build, test that the order is stable, then commit.

### Task 4: Shared prompt rules module

**Files:**
- Create: `backend/app/agent/prompt_rules.py`
- Modify: `backend/app/agent/quick_reply.py` (`FAST_RULES` line 80, `_FILLER_SYSTEM` line 121, `_CARE_FILLER_SYSTEM` line 166), `backend/app/agent/idle_checkin.py` (`_CHECK_IN_SYSTEM` line 43)
- Test: `backend/tests/test_prompt_rules.py` (new), `backend/tests/test_quick_reply.py`, `backend/tests/test_idle_checkin.py`

**Interfaces:**
- Produces, in `app.agent.prompt_rules`, plain `str` constants with no braces:
  - `PACKAGE_WORD`: say প্যাকেজ / package, never প্যাক / pack, in every form (প্যাকেজগুলো, প্যাকেজটা).
  - `BANGLA_WORDS`: use চেক, প্যাকেজ, ব্যালেন্স, রিচার্জ, ডাটা, মিনিট, অফার, কোড, ওকে; avoid bookish words (তথ্য অনুযায়ী, উক্ত, অবশিষ্ট, মিলিয়ে, ঘেঁটে, খুলছি, অনুগ্রহপূর্বক); দাম not প্রাইস.
  - `BRAND`: the operator is "telco", never "telco.".
- Task 6 imports these too. The spec's "digits and units" rule gets no constant: only the main prompt states it (the quick prompts forbid numbers instead), so it stays there.

- [ ] **Step 1: Write the failing tests** in `tests/test_prompt_rules.py`:
  - `test_shared_rules_have_no_braces`: no constant contains `{` or `}`.
  - `test_every_quick_prompt_uses_the_shared_package_rule`: `PACKAGE_WORD` is a substring of `quick_reply._FILLER_SYSTEM`, `quick_reply._CARE_FILLER_SYSTEM` and `idle_checkin._CHECK_IN_SYSTEM`.
  - `test_care_filler_states_the_brand_once`: `BRAND` appears in `_CARE_FILLER_SYSTEM` exactly once.
- [ ] **Step 2: Run them and confirm they fail.** Run: `cd backend && uv run pytest tests/test_prompt_rules.py -q`. Expected: ImportError.
- [ ] **Step 3: Implement.** Create the module. Replace the restated rule text in the three quick prompts and the idle prompt with the constants, then delete the old lines. `_CARE_FILLER_SYSTEM` is an f-string, so interpolate. `_FILLER_SYSTEM` and `_CHECK_IN_SYSTEM` are plain strings that hold literal JSON braces: build them by concatenation, not by an f-string or `.format`.
- [ ] **Step 4: Update the anchors in `test_quick_reply.py::test_filler_examples_are_telco`** to match the shared wording, then run:
  `uv run pytest tests/test_prompt_rules.py tests/test_quick_reply.py tests/test_idle_checkin.py -q`
  Expected: all pass.
- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/agent/prompt_rules.py backend/app/agent/quick_reply.py backend/app/agent/idle_checkin.py backend/tests/test_prompt_rules.py backend/tests/test_quick_reply.py
  git commit -m "refactor(agent): shared prompt rules written once"
  ```

### Task 5: Bench baseline (before any main-prompt change)

**Files:**
- Modify: `scripts/reply_bench/run.py` (add a `--buy` script; add `--out PATH` to also write the transcript to a file)
- Create: `docs/bench/2026-11-06-before/` with one `.txt` per script and run

- [ ] **Step 1:** Start the Telco DB. Run `cd backend && uv run python ../scripts/reply_bench/run.py --guest`. If it prints `NOTE: the dashboard has a customised identity/rules prompt`, stop and ask the user: reset it to the default, or compact that copy too (spec 2.4).
- [ ] **Step 2: Add `BUY_TURNS`** and a `--buy` flag (logged-in customer): `"১ জিবি ডাটা প্যাকেজটা নিতে চাই"`, `"main balance থেকে"`, `"123456"`. A wrong code is fine; the reply must ask for the code first and must not claim success. Add `--out PATH`: the same printout also goes to that file, UTF-8.
- [ ] **Step 3: Record the baseline.** Run each of default, `--guest`, `--sim`, `--packages` and `--buy` twice, with `--out ../docs/bench/2026-11-06-before/<script>-<n>.txt`.
- [ ] **Step 4: Commit**
  ```bash
  git add scripts/reply_bench/run.py docs/bench/2026-11-06-before
  git commit -m "chore(bench): buy script, --out, baseline replies before prompt compaction"
  ```

### Task 6: Compact `DEFAULT_IDENTITY_AND_RULES` behind a rule checklist

**Files:**
- Modify: `backend/app/agent/prompt_defaults.py` (`DEFAULT_IDENTITY_AND_RULES` line 12; `KNOWLEDGE_SCOPE_DEFAULT` and `KNOWLEDGE_SCOPE_RAG` lines 236–278), `backend/app/agent/snapshot.py` (`GUEST_SNAPSHOT`, `_SNAPSHOT_HEAD`) only where they restate main-prompt rules
- Test: `backend/tests/test_prompt_checklist.py` (new), `backend/tests/test_prompts.py`

**Interfaces:**
- Consumes: `prompt_rules.PACKAGE_WORD`, `BANGLA_WORDS`, `BRAND` (Task 4); `persona.build_system_prompt(userdata, config, rag_tool_available=...)`.

- [ ] **Step 1: Write the checklist test first, against today's prompt.** `tests/test_prompt_checklist.py` renders `build_system_prompt` for four cases: logged-in, guest, logged-in with pick `"bn"`, logged-in with pick `"en"`. Build the userdata the way `test_prompts.py` does. One parametrized test, `test_rule_present`, asserts one short anchor per rule, as a case-sensitive substring present in every case:

  | Rule | Anchor |
  |---|---|
  | Bangla default | `Bangla is the default` |
  | other-language line | `I could not understand that. Could you kindly repeat that?` |
  | polite asks | `চাচ্ছেন` and `করবো?` |
  | digits | `Bengali digits` |
  | package wording | `প্যাকেজ` and `never "প্যাক"` |
  | at most 3 | `at most 3` |
  | ask the kind first | `what kind` |
  | ending order | `ENDING A REPLY` |
  | scope | `SCOPE` |
  | grounding | `ACCOUNT SNAPSHOT` and `never guess` |
  | points | `1 point per full ৳10` |
  | code flow | `verify_otp` and `before the tool returns` |
  | security | `never ask for a PIN` |
  | troubleshooting | `explain_deductions` and `check_network_status` |
  | care centres | `find_care_centre` |
  | escalation | `request_human_agent` |
  | boundaries | `BOUNDARIES` |
  | hard rules | `HARD RULE — POLITICS & RELIGION` and `HARD RULE — CONFIDENTIALITY` |
  | date | `CURRENT DATE:` |

  If an anchor doesn't match today's text, use the shortest phrase that does, and keep it through the rewrite. Also add `test_identity_rules_size_budget`: `len(DEFAULT_IDENTITY_AND_RULES) <= 9500`.
- [ ] **Step 2: Run them.** Run: `cd backend && uv run pytest tests/test_prompt_checklist.py -q`. Expected: every `test_rule_present` case PASSES on today's prompt, and only `test_identity_rules_size_budget` FAILS.
- [ ] **Step 3: Rewrite `DEFAULT_IDENTITY_AND_RULES` section by section:**
  - Keep the section order and headings.
  - One example per rule. Drop the language and package-wording restatements; insert `PACKAGE_WORD` and `BRAND` through the module-level string building.
  - ENDING A REPLY keeps steps 1–6, with one example line kept in total.
  - The Global Constraints word-for-word items stay untouched.
  - Then trim `KNOWLEDGE_SCOPE_*` and the snapshot heads only where they repeat a main-prompt rule.
- [ ] **Step 4: Run the checklist and the existing prompt tests:**
  `uv run pytest tests/test_prompt_checklist.py tests/test_prompts.py tests/test_snapshot.py tests/test_snapshot_refresh.py tests/test_quick_reply.py -q`
  Expected: all pass, including `test_prompt_fixed_english`, `test_prompt_fixed_bangla_says_bengali_script` and `test_prompt_unset_unchanged`. Where an old `test_prompts.py` test pins a sentence that was only reworded, update its anchor and say so in the commit message. Never delete a rule to make a test pass.
- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/agent/prompt_defaults.py backend/app/agent/snapshot.py backend/tests/test_prompt_checklist.py backend/tests/test_prompts.py
  git commit -m "refactor(agent): compact identity and rules prompt behind a rule checklist"
  ```

### Task 7: Bench after, compare, restore any regression

**Files:**
- Create: `docs/bench/2026-11-06-after/`, `docs/bench/2026-11-06-compare.md`

- [ ] **Step 1:** Run the same 5 scripts twice each with `--out ../docs/bench/2026-11-06-after/<script>-<n>.txt`.
- [ ] **Step 2: Write `2026-11-06-compare.md`.** Per script, put the before and after replies side by side and mark each turn same, better or worse on:
  - language
  - Bangla register
  - package wording
  - grounded figures (they must match the snapshot)
  - tools called
  - the code flow (asks for the code, no early success)
  - the ending question

  Include the calque counts and "same closing question twice" from the bench footer.
- [ ] **Step 3:** For every "worse" that both after-runs show, restore the old wording for that rule in `prompt_defaults.py`. Re-run Task 6, Step 4, then re-run that script. Repeat until there's no "worse" left that both runs show. A "worse" in only one of the two runs is noted as noise, not fixed.
- [ ] **Step 4:** Record the size in `compare.md`: `len(DEFAULT_IDENTITY_AND_RULES)` before and after, and the first-call tokens in from one bench run each.
- [ ] **Step 5: Commit**
  ```bash
  git add docs/bench backend/app/agent/prompt_defaults.py
  git commit -m "docs(bench): before/after reply comparison for compact prompts"
  ```

### Task 8: Live check and hand-off

- [ ] **Step 1:** Run the test files from the spec's verification list:
  `cd backend && uv run pytest tests/test_turn_gate.py tests/test_gated_session.py tests/test_quick_reply.py tests/test_prefetch.py tests/test_phone_numbers.py tests/test_turn_judge.py tests/test_prompts.py tests/test_snapshot.py tests/test_snapshot_refresh.py tests/test_idle_checkin.py tests/test_run_log.py tests/test_prompt_rules.py tests/test_prompt_checklist.py -q`
  Expected: all pass.
- [ ] **Step 2:** Ask the user for one live voice call (worker restarted). Compare its "AI model" lines and `Prompt cache` row with run_93: tokens in, cached share, time to first words.
- [ ] **Step 3:** Report the numbers and the link to `compare.md` to the user. Ask whether to push the branch.
