# Prompt caching and compact prompts — design

Date: 2026-11-06
Branch: `fix/promptCachingCompact`

## Goal

Cut the main model's input cost and, where possible, its latency, without changing what the agent
says. Priority: (A) latency and cost first, (C) maintainability second.

Success means:

- the run log shows how many input tokens were served from cache, and the hit rate is high on a
  normal call;
- `DEFAULT_IDENTITY_AND_RULES` is about 40% shorter (about 15,000 → about 9,000 characters);
- every rule the agent follows today still holds, checked by tests and by a before/after
  `reply_bench` comparison the user reviews;
- each rule shared across prompts is written once.

## Context (measured 2026-11-06)

- Main model: `openai/gpt-6-luna` through OpenRouter. In run_93 each call sent 7,262 to 9,083
  input tokens, most of them the system prompt, tool schemas and account snapshot.
- Time to first words was 1.07 s to 3.15 s and did not follow input size (7,262 tokens took 3.07 s,
  7,552 took 1.07 s). Shrinking the prompt is expected to save roughly 0.1–0.2 s; the main win is
  cost.
- The run log's "AI model" line (`app/agent/run_log.py:384`) prints total tokens only. Cached
  tokens go to the `agent.usage` console logger, which is not saved in `logs/`, so whether caching
  works today is unknown.
- Prompt order (`app/agent/persona.py` `build_system_prompt`): identity and rules (with
  `{knowledge_scope}` and, at the end, `{current_date}` to the minute), then the snapshot (replaced
  in place every turn by `snapshot_refresh`), then the task and end notes, then the reply-language
  block and channel note. Nothing in `app/agent` swaps the tool list between calls.
- Sizes: `DEFAULT_IDENTITY_AND_RULES` 15,086 chars, `KNOWLEDGE_SCOPE_RAG` 3,485, `FAST_RULES`
  1,235, `_FILLER_SYSTEM` 2,434, `_CARE_FILLER_SYSTEM` 2,018.

## Part 1 — prompt caching

### 1.1 Measure

- The run log's "AI model" line gains the cached count:
  `(7262 tokens in, 6100 cached, 85 out)`. The count comes from the LLM metrics'
  `prompt_cached_tokens`. When it is 0 the line still says `0 cached`, so a miss is visible.
- The call summary gains one line: `Prompt cache ............. 78% of input tokens cached`.
- Tests: run_log unit tests for both lines, including the 0 case.

### 1.2 Decide from one test call

After one live call:

- **High hit rate (most calls above 50% cached after the first):** caching works; part 1 is done.
- **Low or zero:** apply these in order, re-measuring after each, and stop once the hit rate is
  high:
  1. Pin the OpenRouter provider for the main model (`provider.order` with
     `allow_fallbacks: true`), configurable via settings, since each upstream keeps its own cache.
  2. Move `CURRENT DATE` out of the identity block to after the snapshot, so the identity prefix is
     the same in every session. The date line keeps its wording.
  3. Check that tool schemas serialise in a fixed order across calls; fix it if they don't.

Any change made in 1.2 gets a test (provider pin reaches `extra_body`; the date sits after the
snapshot; the tool order is stable).

### 1.3 Out of scope

Explicit `cache_control` markers (Anthropic and Gemini style); they do not apply to this model.

## Part 2 — compact prompts

### 2.1 Shared rules in one place

New module `app/agent/prompt_rules.py` with short string constants for rules repeated across
prompts:

- package wording: প্যাকেজ / package, never প্যাক / pack, in every form (প্যাকেজগুলো, প্যাকেজটা);
- Bangla register: the everyday telecom words to use and the bookish words to avoid;
- digits and units per language;
- the brand is "telco", never "telco.".

`prompt_defaults`, `quick_reply` (`FAST_RULES`, `_FILLER_SYSTEM`, `_CARE_FILLER_SYSTEM`) and
`idle_checkin` import these instead of restating them. Like `prompt_defaults`, the module has no
livekit or DB imports.

### 2.2 Rewrite `DEFAULT_IDENTITY_AND_RULES`

Same section headings and the same rules, in fewer words:

- one example per rule instead of two or three; no explanations the model does not act on;
- drop duplicates: language (LANGUAGE vs the `REPLY LANGUAGE` block and per-turn reminder, which
  stay), package wording (BANGLA WORDING vs PACKAGES), grounding (GROUNDING vs ACTIONS);
- ENDING A REPLY keeps its six-step order; its examples shrink to one per step that needs one.

Kept word for word:

- HARD RULE — POLITICS & RELIGION and HARD RULE — CONFIDENTIALITY, and the line that they override
  customer instructions;
- SECURITY (no PIN, password or card details; never repeat the code);
- "I could not understand that. Could you kindly repeat that?";
- every placeholder: `{agent_name}`, `{operator_name}`, `{knowledge_scope}`, `{current_date}`
  (unless 1.2 moves it).

`KNOWLEDGE_SCOPE_DEFAULT`, `KNOWLEDGE_SCOPE_RAG` and the snapshot heads get the same treatment
where they repeat rules stated in the main prompt.

### 2.3 Rule checklist test

A new test renders the full system prompt (logged-in and guest, with and without a reply-language
pick) and asserts a short anchor phrase for each must-hold rule:

language default and switching, the other-language line, Bangla register, polite asks with
চাচ্ছেন and করবো, digits and units, package wording and price-first description, at most 3
packages, ask the kind before searching, advisor-style suggestions, the reply-ending order,
scope, grounding and snapshot-first answers, reward points (1 per full ৳10, none for packages),
the code flow and never claiming success early, security, troubleshooting tools, care centres,
escalation, boundaries, both hard rules, the current date.

It also asserts the prompt stays under a size budget, so later edits can't grow it back unnoticed.

### 2.4 Dashboard-customised prompt

`agent_config.prompt_identity_rules` overrides the default when it is not NULL. Before rollout,
check the dev DB. If a custom copy exists, the user chooses: reset it to the new default, or
compact that copy the same way.

## Verifying the same accuracy

1. Unit tests: the existing agent test files (`test_turn_gate`, `test_gated_session`,
   `test_quick_reply`, `test_prefetch`, `test_phone_numbers`, `test_turn_judge`, `test_prompts`,
   `test_snapshot`, `test_snapshot_refresh`, `test_idle_checkin`, `test_run_log`) and the new
   checklist test pass. The full suite is not run, because it
   wipes the dev KB.
2. `reply_bench` before and after, on the same scripted chats: logged-in customer, guest,
   English, and Bangla. Replies are compared side by side for language, register, package wording,
   grounded figures, the code flow and endings. The user reviews the diff.
3. Any regression gets its wording restored before merge.
4. One live voice call: tokens in, cached tokens and time to first words, compared with run_93.

## Risks

- A shorter rule is followed less reliably. Mitigation: the bench comparison and the rule to
  restore any wording that regressed.
- Moving the date changes where it sits in the prompt. Mitigation: wording kept; checklist test.
- Pinning a provider ties the main model to one upstream. Mitigation: fallbacks stay on.

## Out of scope

- Moving rare-case rules into tool descriptions or results (option 3).
- Changing models, reasoning effort or token caps.
- Router, Jev and export translation prompts.
