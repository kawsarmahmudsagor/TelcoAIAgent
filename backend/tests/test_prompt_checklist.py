"""Every rule the agent must keep, by a short anchor phrase in the rendered
system prompt. Compacting the prompt may reword a rule but never drop it: a
missing anchor fails here (spec 2026-11-06-prompt-caching-compact, 2.3)."""

import pytest

from app.agent.persona import build_system_prompt
from app.agent.prompt_defaults import DEFAULT_IDENTITY_AND_RULES
from app.agent.userdata import Channel, SessionUserdata
from app.services import agent_config_service

_SNAPSHOT = "ACCOUNT SNAPSHOT — sample demo data.\nName: Test Customer\nBalance: 100 taka"


def _prompt(*, guest: bool = False, lang: str | None = None) -> str:
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None, reply_language=lang)
    if not guest:
        userdata.snapshot_text = _SNAPSHOT
    return build_system_prompt(userdata, agent_config_service.resolve(None), rag_tool_available=True)


_CASES = {
    "logged_in": _prompt(),
    "guest": _prompt(guest=True),
    "pick_bn": _prompt(lang="bn"),
    "pick_en": _prompt(lang="en"),
}

# rule -> anchors that must all appear in every rendered case.
_RULES = {
    "bangla_default": ["Bangla is the default"],
    "other_language_line": ["I could not understand that"],
    "polite_asks": ["চাচ্ছেন", "করবো?"],
    "digits": ["Bengali digits"],
    "package_wording": ["প্যাকেজ", 'never "প্যাক"'],
    "at_most_3": ["at most 3"],
    "price_first": ["price first"],
    "suggestion_ends_with_a_pick": ["ask which they'd like"],
    "intro_once": ["introduce yourself only once"],
    "decline_in_own_voice": ["in your own voice"],
    "brevity": ["Say as much as the question needs"],
    "one_way_to_give_the_code": ["naming one"],
    "missing_recharge_gets_a_case": ["is missing"],
    "ask_kind_first": ["what kind"],
    "ending_order": ["ENDING A REPLY"],
    "scope": ["SCOPE"],
    "grounding": ["ACCOUNT SNAPSHOT", "never guess"],
    "points": ["1 point per full ৳10"],
    "code_flow": ["verify_otp", "before the tool returns"],
    "security": ["never ask for a PIN"],
    "troubleshooting": ["explain_deductions", "check_network_status"],
    "care_centres": ["find_care_centre"],
    "condition_said_to_its_person": ["Say a condition to the person it applies to"],
    "escalation": ["request_human_agent"],
    "boundaries": ["BOUNDARIES"],
    "hard_rules": ["HARD RULE — POLITICS & RELIGION", "HARD RULE — CONFIDENTIALITY"],
    "date": ["CURRENT DATE:"],
}


@pytest.mark.parametrize("case", sorted(_CASES))
@pytest.mark.parametrize("rule", sorted(_RULES))
def test_rule_present(rule, case):
    prompt = _CASES[case]
    missing = [anchor for anchor in _RULES[rule] if anchor not in prompt]
    assert not missing, f"{rule} lost in {case}: {missing}"


def test_identity_rules_size_budget():
    # 15,086 before compaction; 9,500 cut too far (bench 2026-11-06: self-intros,
    # semicolons, ads order and the suggestion's closing question regressed;
    # final review: brevity, one way to give the code, a missing recharge).
    assert len(DEFAULT_IDENTITY_AND_RULES) <= 10300
